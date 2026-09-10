from __future__ import annotations

from .models import ExecutionMode, PageCapabilities, PolicyDecision, SupervisorTurn


PAGE_CAPABILITIES: dict[str, PageCapabilities] = {
    "resume": PageCapabilities(
        modes=frozenset({ExecutionMode.CHAT, ExecutionMode.DIRECT_SKILL, ExecutionMode.FIXED_WORKFLOW, ExecutionMode.AGENT_LOOP,
                         ExecutionMode.CLARIFICATION}),
        skills=frozenset({"direct_chat", "text_rewriter", "resume_reviewer", "resume_writer", "jd_analyzer", "skill_matcher"}),
        workflows=frozenset({"generate_resume"}),
        actions=frozenset({"preview_diff", "apply_resume_patch", "undo_resume_patch"}),
    ),
    "interview-prep": PageCapabilities(
        modes=frozenset({ExecutionMode.CHAT, ExecutionMode.DIRECT_SKILL, ExecutionMode.FIXED_WORKFLOW,
                         ExecutionMode.CLARIFICATION}),
        skills=frozenset({"direct_chat", "interview_coach", "jd_analyzer"}),
        workflows=frozenset({"prepare_interview"}),
    ),
    "ai-coding": PageCapabilities(
        modes=frozenset({ExecutionMode.CHAT, ExecutionMode.DIRECT_SKILL, ExecutionMode.CLARIFICATION}),
        skills=frozenset({"direct_chat", "interview_coach"}),
    ),
    "job-radar": PageCapabilities(
        modes=frozenset({ExecutionMode.CHAT, ExecutionMode.DIRECT_SKILL, ExecutionMode.CLARIFICATION}),
        skills=frozenset({"direct_chat", "jd_analyzer", "skill_matcher", "career_advisor", "job_recommender", "job_radar_query"}),
        actions=frozenset({"favorite_job", "not_interested_job", "track_job"}),
    ),
}


class AssistantPolicyEngine:
    def authorize(self, page: str, turn: SupervisorTurn) -> PolicyDecision:
        capabilities = PAGE_CAPABILITIES.get(page)
        if capabilities is None:
            return PolicyDecision(allowed=False, effective_mode=ExecutionMode.CHAT,
                                  reason_code="page_has_no_assistant")
        if turn.kind == "final_response":
            return PolicyDecision(allowed=True, effective_mode=ExecutionMode.CHAT,
                                  reason_code=turn.reason_code)
        if turn.kind == "clarification":
            return PolicyDecision(allowed=True, effective_mode=ExecutionMode.CLARIFICATION,
                                  reason_code=turn.reason_code)
        if turn.kind == "skill_call":
            allowed = bool(turn.name and turn.name in capabilities.skills)
            mode = ExecutionMode.CHAT if turn.name == "direct_chat" else ExecutionMode.DIRECT_SKILL
            return PolicyDecision(allowed=allowed, effective_mode=mode,
                                  reason_code=turn.reason_code if allowed else "skill_not_allowed")
        if turn.kind == "workflow_call":
            allowed = bool(turn.name and turn.name in capabilities.workflows)
            return PolicyDecision(allowed=allowed, effective_mode=ExecutionMode.FIXED_WORKFLOW,
                                  reason_code=turn.reason_code if allowed else "workflow_not_allowed")
        allowed = bool(turn.name and turn.name in capabilities.actions)
        return PolicyDecision(allowed=allowed, effective_mode=ExecutionMode.DIRECT_SKILL,
                              requires_confirmation=allowed,
                              reason_code=turn.reason_code if allowed else "action_not_allowed")
