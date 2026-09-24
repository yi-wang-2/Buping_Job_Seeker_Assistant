from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Interrupt, Send, interrupt

from .models import ExecutionMode, PolicyDecision, SupervisorTurn
from .policy import AssistantPolicyEngine


class AssistantGraphState(TypedDict, total=False):
    session_id: str
    page: str
    request: dict[str, Any]
    task_type: str
    task_parameters: dict[str, Any]
    route: dict[str, Any] | None
    observations: list[dict[str, Any]]
    pending_input: dict[str, Any] | None
    result: dict[str, Any] | None
    policy: dict[str, Any] | None
    error: dict[str, Any] | None
    steps: int
    replans: int
    total_tokens: int
    terminal_reason: str
    dispatch_path: str


class SafeJsonSerializer:
    """Serialize checkpoint channel values without Python object reconstruction."""

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        return "json", json.dumps(
            self._encode(obj), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")

    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        kind, payload = data
        if kind != "json":
            raise ValueError(f"Unsupported checkpoint payload type: {kind}")
        return self._decode(json.loads(payload.decode("utf-8")))

    @classmethod
    def _encode(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): cls._encode(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._encode(item) for item in value]
        if isinstance(value, Interrupt):
            return {
                "__buping_type__": "langgraph.Interrupt", "value": cls._encode(value.value),
                "resumable": value.resumable, "ns": cls._encode(value.ns), "when": value.when,
            }
        if isinstance(value, Send):
            return {"__buping_type__": "langgraph.Send", "node": value.node, "arg": cls._encode(value.arg)}
        raise TypeError(f"Checkpoint value is not in the safe JSON allowlist: {type(value).__name__}")

    @classmethod
    def _decode(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [cls._decode(item) for item in value]
        if not isinstance(value, dict):
            return value
        kind = value.get("__buping_type__")
        if kind == "langgraph.Interrupt":
            return Interrupt(
                value=cls._decode(value.get("value")), resumable=bool(value.get("resumable")),
                ns=cls._decode(value.get("ns")), when=value.get("when") or "during",
            )
        if kind == "langgraph.Send":
            return Send(str(value.get("node") or ""), cls._decode(value.get("arg")))
        if kind:
            raise ValueError(f"Unsupported checkpoint object type: {kind}")
        return {key: cls._decode(item) for key, item in value.items()}


@dataclass(frozen=True, slots=True)
class GraphOutcome:
    dispatch_path: str
    mode: ExecutionMode
    turn: SupervisorTurn | None = None
    result: dict[str, Any] | None = None
    policy: PolicyDecision | None = None
    error_code: str = ""
    steps: tuple[dict[str, Any], ...] = ()
    terminal_reason: str = "completed"
    interrupted: bool = False
    resumed: bool = False


REPORT_DIMENSIONS = (
    "location", "industry", "company_type", "recruitment_type", "scene", "match_level", "company"
)


def is_job_market_report_request(page: str, message: str) -> bool:
    if page != "job-radar":
        return False
    normalized = "".join(message.lower().split())
    report_terms = ("就业形势", "总体报告", "整体报告", "全维度", "所有维度", "岗位形势", "招聘形势")
    return any(term in normalized for term in report_terms)


def normalize_report_dimensions(message: str) -> list[str]:
    normalized = "".join(message.lower().split())
    if any(term in normalized for term in ("所有维度", "全部维度", "全维度", "总体报告", "整体报告")):
        return list(REPORT_DIMENSIONS)
    aliases = {
        "location": ("城市", "地区", "地点"),
        "industry": ("行业",),
        "company_type": ("公司类型", "企业类型", "国企", "外企", "民企"),
        "recruitment_type": ("招聘类型", "秋招", "校招", "社招"),
        "scene": ("场景", "公务员", "事业单位"),
        "match_level": ("匹配度", "匹配"),
        "company": ("公司分布", "企业分布", "公司排名"),
    }
    return [key for key, terms in aliases.items() if any(term in normalized for term in terms)]


class AssistantGraphFacade:
    """LangGraph orchestration facade around the existing Skills and domain services."""

    def __init__(
        self,
        checkpoint_path: str | Path,
        *,
        supervisor: Callable[[list[dict[str, Any]], dict[str, Any]], SupervisorTurn],
        executor: Callable[[SupervisorTurn, dict[str, Any]], dict[str, Any]],
        policy: AssistantPolicyEngine | None = None,
        max_steps: int = 5,
        max_replans: int = 1,
        max_tokens: int = 12000,
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.supervisor = supervisor
        self.executor = executor
        self.policy = policy or AssistantPolicyEngine()
        self.max_steps = max_steps
        self.max_replans = max_replans
        self.max_tokens = max_tokens

    def _compile(self, connection: sqlite3.Connection):
        builder = StateGraph(AssistantGraphState)
        builder.add_node("route_node", self._route)
        builder.add_node("policy_node", self._policy)
        builder.add_node("clarify", self._clarify)
        builder.add_node("execute", self._execute)
        builder.add_node("approval", self._approval)
        builder.add_edge(START, "route_node")
        builder.add_edge("route_node", "policy_node")
        builder.add_conditional_edges("policy_node", self._after_policy, {
            "clarify": "clarify", "execute": "execute", "end": END,
        })
        builder.add_edge("clarify", "route_node")
        builder.add_conditional_edges("execute", self._after_execute, {
            "route": "route_node", "approval": "approval", "end": END,
        })
        builder.add_edge("approval", END)
        saver = SqliteSaver(connection, serde=SafeJsonSerializer())
        return builder.compile(checkpointer=saver)

    def _route(self, state: AssistantGraphState) -> dict[str, Any]:
        request = dict(state.get("request") or {})
        message = str(request.get("message") or "")
        page = str(state.get("page") or request.get("page") or "")
        if is_job_market_report_request(page, message) or state.get("task_type") == "job_market_report":
            dimensions = normalize_report_dimensions(message)
            if not dimensions:
                turn = SupervisorTurn(
                    kind="clarification", intent="job_market_report", response=(
                        "你希望按哪些维度分析？可以回复“所有维度”，或指定城市、行业、公司类型、招聘类型、场景、匹配度和公司分布。"
                    ), reason_code="job_report_dimensions_required",
                )
                return {
                    "task_type": "job_market_report", "route": turn.model_dump(mode="json"),
                    "pending_input": {"field": "dimensions", "question": turn.response},
                    "dispatch_path": "deterministic_subgraph",
                }
            turn = SupervisorTurn(
                kind="workflow_call", intent="job_market_report", name="job_market_report",
                arguments={"dimensions": dimensions}, reason_code="deterministic_job_market_report",
            )
            return {
                "task_type": "job_market_report", "task_parameters": {"dimensions": dimensions},
                "route": turn.model_dump(mode="json"), "pending_input": None,
                "dispatch_path": "deterministic_subgraph",
            }
        turn = self.supervisor(list(state.get("observations") or []), request)
        return {"route": turn.model_dump(mode="json"), "dispatch_path": "supervisor"}

    def _policy(self, state: AssistantGraphState) -> dict[str, Any]:
        try:
            turn = SupervisorTurn.model_validate(state.get("route"))
            decision = self.policy.authorize(str(state.get("page") or ""), turn)
            if not decision.allowed:
                return {
                    "policy": decision.model_dump(mode="json"),
                    "error": {"code": decision.reason_code, "message": "Request rejected by policy"},
                    "terminal_reason": "policy_rejected",
                }
            return {"policy": decision.model_dump(mode="json"), "error": None}
        except Exception as exc:
            return {
                "error": {"code": "invalid_route", "message": str(exc)},
                "terminal_reason": "invalid_route",
            }

    @staticmethod
    def _after_policy(state: AssistantGraphState) -> str:
        if state.get("error"):
            return "end"
        turn = SupervisorTurn.model_validate(state.get("route"))
        if turn.kind == "clarification":
            return "clarify"
        if turn.kind == "final_response":
            return "end"
        return "execute"

    @staticmethod
    def _clarify(state: AssistantGraphState) -> dict[str, Any]:
        pending = dict(state.get("pending_input") or {})
        turn = SupervisorTurn.model_validate(state.get("route"))
        answer = interrupt({
            "kind": "clarification", "task_type": state.get("task_type") or turn.intent,
            "field": pending.get("field") or "details", "question": pending.get("question") or turn.response,
        })
        request = dict(state.get("request") or {})
        original = str(request.get("message") or "").strip()
        request["message"] = f"{original}\n用户补充：{str(answer).strip()}".strip()
        return {"request": request, "route": None, "pending_input": None}

    def _execute(self, state: AssistantGraphState) -> dict[str, Any]:
        turn = SupervisorTurn.model_validate(state.get("route"))
        result = self.executor(turn, dict(state.get("request") or {}))
        usage = dict(result.get("usage") or {})
        observations = list(state.get("observations") or [])
        observations.append({
            "step": len(observations) + 1, "kind": turn.kind, "name": turn.name,
            "status": "degraded" if result.get("degraded") else "completed",
            "summary": str(result.get("content") or result.get("observation") or "")[:2000],
        })
        return {
            "result": result, "observations": observations, "steps": int(state.get("steps") or 0) + 1,
            "replans": int(state.get("replans") or 0) + (1 if turn.continue_run else 0),
            "total_tokens": int(state.get("total_tokens") or 0) + int(usage.get("total_tokens") or 0),
        }

    def _after_execute(self, state: AssistantGraphState) -> str:
        turn = SupervisorTurn.model_validate(state.get("route"))
        result = dict(state.get("result") or {})
        if result.get("proposal"):
            return "approval"
        if not turn.continue_run or turn.kind in {"workflow_call", "action_proposal"}:
            return "end"
        if (
            int(state.get("steps") or 0) >= self.max_steps
            or int(state.get("replans") or 0) > self.max_replans
            or int(state.get("total_tokens") or 0) >= self.max_tokens
        ):
            return "end"
        return "route"

    @staticmethod
    def _approval(state: AssistantGraphState) -> dict[str, Any]:
        proposal = dict((state.get("result") or {}).get("proposal") or {})
        decision = interrupt({
            "kind": "approval", "proposal_id": proposal.get("id"),
            "proposal_type": proposal.get("proposal_type"), "risk": proposal.get("risk"),
        })
        approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
        return {"terminal_reason": "proposal_applied" if approved else "proposal_dismissed"}

    def invoke(self, *, session_id: str, page: str, request: dict[str, Any]) -> GraphOutcome:
        connection = sqlite3.connect(self.checkpoint_path, check_same_thread=False)
        try:
            graph = self._compile(connection)
            config = {"configurable": {"thread_id": f"assistant-v2:{session_id}", "checkpoint_ns": ""}}
            snapshot = graph.get_state(config)
            if snapshot.next and "approval" in snapshot.next:
                state = dict(snapshot.values or {})
                route = state.get("route")
                turn = SupervisorTurn.model_validate(route) if route else None
                policy_data = state.get("policy")
                policy = PolicyDecision.model_validate(policy_data) if policy_data else None
                return GraphOutcome(
                    dispatch_path=str(state.get("dispatch_path") or "supervisor"),
                    mode=policy.effective_mode if policy else ExecutionMode.DIRECT_SKILL,
                    turn=turn, result=dict(state.get("result") or {}), policy=policy,
                    error_code="pending_confirmation", steps=tuple(state.get("observations") or []),
                    terminal_reason="pending_confirmation", interrupted=True,
                )
            resumed = bool(snapshot.next and "clarify" in snapshot.next)
            graph_input: AssistantGraphState | Command
            if resumed:
                graph_input = Command(resume=str(request.get("message") or ""))
            else:
                graph_input = {
                    "session_id": session_id, "page": page, "request": request,
                    # A completed checkpoint starts a new turn on the same thread.  Explicitly
                    # clear transient channels so the new request cannot inherit the previous
                    # task's route, policy, result, or error through LangGraph's state merge.
                    "task_type": "", "task_parameters": {}, "route": None,
                    "observations": [], "steps": 0, "replans": 0, "total_tokens": 0,
                    "pending_input": None, "result": None, "policy": None, "error": None,
                    "dispatch_path": "supervisor", "terminal_reason": "completed",
                }
            result = graph.invoke(graph_input, config=config)
            final_snapshot = graph.get_state(config)
            interrupts = result.get("__interrupt__") or tuple(
                interrupt_item
                for task in final_snapshot.tasks
                for interrupt_item in task.interrupts
            )
            is_interrupted = bool(interrupts or (final_snapshot.next and "clarify" in final_snapshot.next))
            route = result.get("route")
            turn = SupervisorTurn.model_validate(route) if route else None
            policy_data = result.get("policy")
            policy = PolicyDecision.model_validate(policy_data) if policy_data else None
            error = dict(result.get("error") or {})
            mode = policy.effective_mode if policy else ExecutionMode.CLARIFICATION if is_interrupted else ExecutionMode.CHAT
            return GraphOutcome(
                dispatch_path=str(result.get("dispatch_path") or "supervisor"), mode=mode, turn=turn,
                result=dict(result.get("result") or {}), policy=policy,
                error_code=str(error.get("code") or ""), steps=tuple(result.get("observations") or []),
                terminal_reason=str(result.get("terminal_reason") or "completed"),
                interrupted=is_interrupted, resumed=resumed,
            )
        finally:
            connection.close()

    def resume_approval(self, *, session_id: str, approved: bool) -> dict[str, Any] | None:
        connection = sqlite3.connect(self.checkpoint_path, check_same_thread=False)
        try:
            graph = self._compile(connection)
            config = {"configurable": {"thread_id": f"assistant-v2:{session_id}", "checkpoint_ns": ""}}
            snapshot = graph.get_state(config)
            if "approval" not in snapshot.next:
                return None
            return graph.invoke(Command(resume={"approved": approved}), config=config)
        finally:
            connection.close()
