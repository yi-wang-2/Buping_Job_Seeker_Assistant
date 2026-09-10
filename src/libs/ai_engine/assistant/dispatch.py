from __future__ import annotations

from .models import DispatchDecision, DispatchInput
from .policy import PAGE_CAPABILITIES


class DispatchPolicy:
    """Deterministic fast path. It never interprets free-form language."""

    def decide(self, request: DispatchInput) -> DispatchDecision:
        capabilities = PAGE_CAPABILITIES.get(request.page)
        if capabilities is None:
            return DispatchDecision(path="reject", reason_code="page_has_no_assistant")
        if request.input_type == "natural_language":
            if not request.message.strip():
                return DispatchDecision(path="reject", reason_code="empty_message")
            return DispatchDecision(path="supervisor", reason_code="natural_language")
        if not request.action or request.action not in capabilities.actions:
            return DispatchDecision(path="reject", action=request.action, reason_code="action_not_allowed")
        if request.active_run:
            return DispatchDecision(path="reject", action=request.action, reason_code="active_run_conflict")
        return DispatchDecision(path="deterministic", action=request.action, reason_code="explicit_ui_action")

