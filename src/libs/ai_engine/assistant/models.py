from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExecutionMode(str, Enum):
    CHAT = "chat"
    DIRECT_SKILL = "direct_skill"
    FIXED_WORKFLOW = "fixed_workflow"
    AGENT_LOOP = "agent_loop"
    CLARIFICATION = "clarification"


class PageCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    modes: frozenset[ExecutionMode]
    skills: frozenset[str] = frozenset()
    workflows: frozenset[str] = frozenset()
    actions: frozenset[str] = frozenset()


class DispatchInput(BaseModel):
    input_type: Literal["ui_action", "natural_language"] = "natural_language"
    action: str | None = None
    message: str = ""
    page: str
    page_mode: str = ""
    selected_objects: list[str] = Field(default_factory=list)
    active_run: bool = False


class DispatchDecision(BaseModel):
    path: Literal["deterministic", "supervisor", "reject"]
    action: str | None = None
    reason_code: str


class SupervisorInput(BaseModel):
    message: str
    page: str
    selected_objects: list[str] = Field(default_factory=list)
    available_skills: list[str] = Field(default_factory=list)
    available_workflows: list[str] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)
    conversation_summary: str = ""
    workspace_snapshot: dict[str, Any] = Field(default_factory=dict)
    observations: list[dict[str, Any]] = Field(default_factory=list)


class SupervisorTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "final_response", "clarification", "skill_call", "workflow_call", "action_proposal"
    ]
    intent: str
    target_refs: list[str] = Field(default_factory=list)
    name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    response: str = ""
    follow_up: str = ""
    reason_code: str
    continue_run: bool = False
    plan: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_discriminated_route(self) -> "SupervisorTurn":
        named_kinds = {"skill_call", "workflow_call", "action_proposal"}
        if self.kind in named_kinds and not str(self.name or "").strip():
            raise ValueError(f"name is required for {self.kind}")
        if self.kind in {"final_response", "clarification"} and self.name is not None:
            raise ValueError(f"name must be null for {self.kind}")
        if self.kind == "clarification" and not self.response.strip():
            raise ValueError("response is required for clarification")
        return self


class PolicyDecision(BaseModel):
    allowed: bool
    effective_mode: ExecutionMode
    requires_confirmation: bool = False
    reason_code: str
