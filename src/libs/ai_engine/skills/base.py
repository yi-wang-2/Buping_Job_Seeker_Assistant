from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

from ..context import ContextItem, TokenBudget
from ..memory import MemoryItem
from ..models import LLMResponse, Message, TokenUsage
from ..presentation.models import ResponseDocument


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


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
    context_minimums: dict[str, int] | None = None
    context_providers: tuple[str, ...] = ()
    prompt_version: str = "1"
    schema_version: str = "1"
    input_schema: type[BaseModel] | None = None
    output_schema: type[BaseModel] | None = None
    temperature: float = 0.4
    timeout_seconds: float = 120.0
    cache_ttl_seconds: int = 86400
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Skill name cannot be empty")
        if not self.version.strip():
            raise ValueError("Skill version cannot be empty")
        if not 0 <= self.temperature <= 2:
            raise ValueError("Skill temperature must be between 0 and 2")
        if self.timeout_seconds <= 0:
            raise ValueError("Skill timeout_seconds must be positive")
        if self.cache_ttl_seconds <= 0:
            raise ValueError("Skill cache_ttl_seconds must be positive")


@dataclass(frozen=True, slots=True)
class SkillResult:
    content: str
    structured_output: Any = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    cached_usage: TokenUsage = field(default_factory=TokenUsage)
    cache_hit: bool = False
    memories_used: tuple[str, ...] = ()
    memory_writes: tuple[MemoryItem, ...] = ()
    warnings: tuple[str, ...] = ()
    trace_id: str = ""
    run_id: str = ""
    presentation: ResponseDocument | None = None
    tool_results: tuple[dict[str, Any], ...] = ()
    context_metadata: dict[str, Any] = field(default_factory=dict)


class Skill(Protocol):
    metadata: SkillMetadata

    def validate_input(self, inputs: dict[str, Any]) -> None: ...
    def context_items(self, inputs: dict[str, Any]) -> list[ContextItem]: ...
    def build_messages(self, inputs: dict[str, Any], context: tuple[ContextItem, ...]) -> tuple[Message, ...]: ...
    def parse_output(self, response: LLMResponse) -> SkillResult: ...
    def validate_output(self, result: SkillResult, inputs: dict[str, Any]) -> None: ...
    def extract_memories(self, result: SkillResult, inputs: dict[str, Any]) -> tuple[MemoryItem, ...]: ...

