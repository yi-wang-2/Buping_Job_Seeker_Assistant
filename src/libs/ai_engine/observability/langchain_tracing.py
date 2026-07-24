from __future__ import annotations

import time
import uuid
from typing import Any

from ..models import LLMRequest, Message
from ..providers.gateway import LLMGateway
from .tracing import JsonlTraceSink, TraceSink


class TracedChatClient:
    """Record a direct LangChain chat-model invocation in the common usage log."""

    def __init__(
        self,
        client: Any,
        *,
        provider: str,
        model: str,
        skill: str,
        temperature: float,
        max_output_tokens: int,
        trace_sink: TraceSink | None = None,
    ) -> None:
        self.client = client
        self.provider = provider
        self.model = model
        self.skill = skill
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.trace_sink = trace_sink or JsonlTraceSink()

    def invoke(self, messages: Any, *, trace_metadata: dict[str, Any] | None = None) -> Any:
        # Trace output contains metadata only; prompt content is deliberately omitted.
        request = LLMRequest(
            messages=(Message("user", "[content omitted]"),),
            model=self.model,
            provider=self.provider,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            metadata={"skill": self.skill, **(trace_metadata or {})},
        )
        trace_id = str(uuid.uuid4())
        started = time.perf_counter()
        try:
            raw = self.client.invoke(messages)
            response = LLMGateway._normalize_response(raw, request, retries=0, started=started)
            self.trace_sink.record(trace_id, request, response=response)
            return raw
        except Exception as exc:
            self.trace_sink.record(trace_id, request, error=exc)
            raise


class GatewayChatClient:
    """Compatibility adapter for legacy code that calls ``chat.invoke``."""

    def __init__(self, gateway: LLMGateway, *, provider: str, model: str, skill: str,
                 temperature: float, max_output_tokens: int) -> None:
        self.gateway = gateway
        self.provider = provider
        self.model = model
        self.skill = skill
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

    @staticmethod
    def _message(value: Any) -> Message:
        if isinstance(value, dict):
            role = str(value.get("role") or value.get("type") or "user")
            content = value.get("content", "")
        else:
            role = str(getattr(value, "type", None) or getattr(value, "role", None) or "user")
            content = getattr(value, "content", value)
        role = {"human": "user", "ai": "assistant"}.get(role, role)
        if role not in {"system", "user", "assistant", "tool"}:
            role = "user"
        return Message(role, str(content))

    def invoke(self, messages: Any, *, trace_metadata: dict[str, Any] | None = None) -> Any:
        values = messages if isinstance(messages, (list, tuple)) else [messages]
        return self.gateway.invoke(LLMRequest(
            messages=tuple(self._message(value) for value in values),
            model=self.model,
            provider=self.provider,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            metadata={"skill": self.skill, **(trace_metadata or {})},
        ))
