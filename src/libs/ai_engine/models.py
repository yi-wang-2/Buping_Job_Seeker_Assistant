from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str
    name: str | None = None

    def as_dict(self) -> dict[str, str]:
        result = {"role": self.role, "content": self.content}
        if self.name:
            result["name"] = self.name
        return result


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if min(self.input_tokens, self.output_tokens, self.total_tokens) < 0:
            raise ValueError("Token usage cannot be negative")
        if not self.total_tokens and (self.input_tokens or self.output_tokens):
            object.__setattr__(self, "total_tokens", self.input_tokens + self.output_tokens)


@dataclass(frozen=True, slots=True)
class LLMRequest:
    messages: tuple[Message, ...]
    model: str
    provider: str
    temperature: float = 0.4
    max_output_tokens: int = 4096
    timeout_seconds: float = 120.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("At least one message is required")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")


@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str
    model: str
    provider: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    finish_reason: str = ""
    response_id: str = ""
    latency_ms: int = 0
    retries: int = 0
    raw_metadata: dict[str, Any] = field(default_factory=dict)

