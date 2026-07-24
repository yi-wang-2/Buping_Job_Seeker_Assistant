from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..context import ContextItem, TokenBudget
from ..models import LLMResponse, Message, TokenUsage


@dataclass(frozen=True, slots=True)
class SkillMetadata:
    name: str
    version: str
    description: str
    token_budget: TokenBudget = field(default_factory=TokenBudget)
    tools: tuple[str, ...] = ()
    memory_read: tuple[str, ...] = ()
    memory_write: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    cacheable: bool = True
    context_weights: dict[str, float] | None = None


@dataclass(frozen=True, slots=True)
class SkillResult:
    content: str
    structured_output: Any = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    cache_hit: bool = False
    memories_used: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    trace_id: str = ""


class Skill(Protocol):
    metadata: SkillMetadata

    def validate_input(self, inputs: dict[str, Any]) -> None: ...
    def context_items(self, inputs: dict[str, Any]) -> list[ContextItem]: ...
    def build_messages(self, inputs: dict[str, Any], context: tuple[ContextItem, ...]) -> tuple[Message, ...]: ...
    def parse_output(self, response: LLMResponse) -> SkillResult: ...

