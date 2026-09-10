from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable

from .dispatch import DispatchPolicy
from .models import DispatchInput, ExecutionMode, PolicyDecision, SupervisorTurn
from .policy import AssistantPolicyEngine


@dataclass(frozen=True, slots=True)
class ControllerOutcome:
    dispatch_path: str
    mode: ExecutionMode
    turn: SupervisorTurn | None = None
    result: dict[str, Any] | None = None
    policy: PolicyDecision | None = None
    error_code: str = ""
    steps: tuple[dict[str, Any], ...] = ()
    terminal_reason: str = "completed"


class AssistantController:
    """Owns a bounded run while model reasoning stays behind callbacks."""

    def __init__(self, dispatch: DispatchPolicy | None = None,
                 policy: AssistantPolicyEngine | None = None, *, max_steps: int = 5,
                 max_replans: int = 1, max_tokens: int = 12000,
                 timeout_seconds: float = 180.0) -> None:
        self.dispatch = dispatch or DispatchPolicy()
        self.policy = policy or AssistantPolicyEngine()
        self.max_steps = max(1, max_steps)
        self.max_replans = max(0, max_replans)
        self.max_tokens = max(1, max_tokens)
        self.timeout_seconds = max(1.0, timeout_seconds)

    def handle(
        self,
        request: DispatchInput,
        *,
        supervisor: Callable[[], SupervisorTurn],
        executor: Callable[[SupervisorTurn], dict[str, Any]],
        replanner: Callable[[list[dict[str, Any]]], SupervisorTurn] | None = None,
    ) -> ControllerOutcome:
        decision = self.dispatch.decide(request)
        if decision.path == "reject":
            return ControllerOutcome(decision.path, ExecutionMode.CHAT, error_code=decision.reason_code)
        if decision.path == "deterministic":
            turn = SupervisorTurn(kind="action_proposal", intent=decision.action or "", name=decision.action,
                                  reason_code=decision.reason_code)
        else:
            turn = supervisor()
        steps: list[dict[str, Any]] = []
        fingerprints: set[str] = set()
        total_tokens = 0
        replans = 0
        started = time.monotonic()
        while True:
            policy = self.policy.authorize(request.page, turn)
            if not policy.allowed:
                return ControllerOutcome(decision.path, policy.effective_mode, turn=turn, policy=policy,
                                         error_code=policy.reason_code, steps=tuple(steps), terminal_reason="policy_rejected")
            if turn.kind in {"final_response", "clarification"}:
                mode = ExecutionMode.AGENT_LOOP if steps else policy.effective_mode
                return ControllerOutcome(decision.path, mode, turn=turn, policy=policy,
                                         steps=tuple(steps), terminal_reason="completed")
            fingerprint = repr((turn.kind, turn.name, sorted(turn.arguments.items())))
            if fingerprint in fingerprints:
                return ControllerOutcome(decision.path, ExecutionMode.AGENT_LOOP, turn=turn, policy=policy,
                                         error_code="repeated_step", steps=tuple(steps), terminal_reason="duplicate_guard")
            fingerprints.add(fingerprint)
            result = executor(turn)
            usage = result.get("usage") or {}
            total_tokens += int(usage.get("total_tokens", 0))
            observation = {
                "step": len(steps) + 1, "kind": turn.kind, "name": turn.name,
                "status": "degraded" if result.get("degraded") else "completed",
                "summary": str(result.get("content") or result.get("observation") or "")[:2000],
            }
            steps.append(observation)
            must_stop = (
                not turn.continue_run or turn.kind in {"workflow_call", "action_proposal"}
                or bool(result.get("proposal"))
            )
            if must_stop:
                mode = ExecutionMode.AGENT_LOOP if len(steps) > 1 else policy.effective_mode
                return ControllerOutcome(decision.path, mode, turn=turn, result=result, policy=policy,
                                         steps=tuple(steps), terminal_reason="completed")
            if not replanner:
                return ControllerOutcome(decision.path, policy.effective_mode, turn=turn, result=result, policy=policy,
                                         steps=tuple(steps), error_code="replanner_unavailable",
                                         terminal_reason="replanner_unavailable")
            if len(steps) >= self.max_steps or replans >= self.max_replans or total_tokens >= self.max_tokens \
                    or time.monotonic() - started >= self.timeout_seconds:
                return ControllerOutcome(decision.path, ExecutionMode.AGENT_LOOP, turn=turn, result=result, policy=policy,
                                         steps=tuple(steps), error_code="agent_budget_exhausted",
                                         terminal_reason="budget_exhausted")
            replans += 1
            turn = replanner(steps)
