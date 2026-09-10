from src.libs.ai_engine.assistant import AssistantController, AssistantPolicyEngine, DispatchInput, DispatchPolicy
from src.libs.ai_engine.assistant.models import ExecutionMode, SupervisorTurn


def test_dispatch_policy_separates_ui_actions_and_natural_language():
    policy = DispatchPolicy()

    natural = policy.decide(DispatchInput(page="resume", message="帮我润色"))
    explicit = policy.decide(DispatchInput(
        page="resume", input_type="ui_action", action="apply_resume_patch",
    ))
    blocked = policy.decide(DispatchInput(
        page="resume", input_type="ui_action", action="apply_resume_patch", active_run=True,
    ))

    assert natural.path == "supervisor"
    assert explicit.path == "deterministic"
    assert blocked.path == "reject"
    assert blocked.reason_code == "active_run_conflict"


def test_policy_rejects_cross_page_skill_even_if_supervisor_requests_it():
    decision = AssistantPolicyEngine().authorize(
        "interview-prep",
        SupervisorTurn(
            kind="skill_call", intent="rewrite", name="text_rewriter",
            reason_code="single_explicit_edit",
        ),
    )

    assert not decision.allowed
    assert decision.reason_code == "skill_not_allowed"


def test_controller_does_not_execute_direct_chat():
    executed = []
    controller = AssistantController(max_steps=1)
    result = controller.handle(
        DispatchInput(page="resume", message="为什么项目描述不够好？"),
        supervisor=lambda: SupervisorTurn(
            kind="final_response", intent="explain", response="缺少结果和证据。",
            reason_code="informational_request",
        ),
        executor=lambda turn: executed.append(turn) or {},
    )

    assert result.mode == ExecutionMode.CHAT
    assert result.turn and result.turn.response == "缺少结果和证据。"
    assert executed == []


def test_controller_executes_only_one_authorized_skill():
    calls = []
    result = AssistantController(max_steps=1).handle(
        DispatchInput(page="resume", message="润色选中文字", selected_objects=["resume.selection"]),
        supervisor=lambda: SupervisorTurn(
            kind="skill_call", intent="rewrite", name="text_rewriter",
            arguments={"mode": "more_professional"}, reason_code="single_explicit_edit",
        ),
        executor=lambda turn: calls.append(turn.name) or {"content": "rewritten"},
    )

    assert result.mode == ExecutionMode.DIRECT_SKILL
    assert result.result == {"content": "rewritten"}
    assert calls == ["text_rewriter"]


def test_direct_chat_responder_executes_as_chat_mode():
    calls = []
    result = AssistantController(max_steps=1).handle(
        DispatchInput(page="job-radar", message="匹配分是什么意思？"),
        supervisor=lambda: SupervisorTurn(
            kind="skill_call", intent="explain", name="direct_chat",
            reason_code="informational_request",
        ),
        executor=lambda turn: calls.append(turn.name) or {"content": "解释结果"},
    )

    assert result.mode == ExecutionMode.CHAT
    assert calls == ["direct_chat"]


def test_controller_replans_bounded_read_only_agent_loop():
    calls = []
    result = AssistantController(max_steps=3, max_replans=1).handle(
        DispatchInput(page="resume", message="先检查再总结"),
        supervisor=lambda: SupervisorTurn(
            kind="skill_call", intent="review", name="resume_reviewer",
            reason_code="multi_step_review", continue_run=True,
            plan=["检查简历", "汇总结论"],
        ),
        executor=lambda turn: calls.append(turn.name) or {"content": "已检查", "usage": {"total_tokens": 20}},
        replanner=lambda observations: SupervisorTurn(
            kind="final_response", intent="summarize", response="检查完成。",
            reason_code="observation_complete",
        ),
    )

    assert result.mode == ExecutionMode.AGENT_LOOP
    assert result.terminal_reason == "completed"
    assert result.steps[0]["name"] == "resume_reviewer"
    assert calls == ["resume_reviewer"]


def test_controller_stops_agent_loop_when_budget_is_exhausted():
    result = AssistantController(max_steps=1, max_replans=1).handle(
        DispatchInput(page="resume", message="执行多步检查"),
        supervisor=lambda: SupervisorTurn(
            kind="skill_call", intent="review", name="resume_reviewer",
            reason_code="multi_step_review", continue_run=True,
        ),
        executor=lambda turn: {"content": "partial", "usage": {"total_tokens": 20}},
        replanner=lambda observations: SupervisorTurn(
            kind="final_response", intent="done", response="done", reason_code="done",
        ),
    )

    assert result.error_code == "agent_budget_exhausted"
    assert result.terminal_reason == "budget_exhausted"
