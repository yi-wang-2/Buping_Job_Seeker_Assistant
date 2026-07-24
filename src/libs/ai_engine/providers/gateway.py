from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from ..exceptions import ProviderConfigurationError, ProviderInvocationError
from ..models import LLMRequest, LLMResponse, TokenUsage
from ..observability.tracing import TraceSink
from .base import ChatClient, ClientFactory


@dataclass(frozen=True, slots=True)
class GatewayConfig:
    api_key: str = ""
    base_url: str = ""
    max_retries: int = 2
    retry_backoff_seconds: float = 0.25


class LLMGateway:
    """Provider-neutral, bounded-retry entry point for chat model calls."""

    def __init__(
        self,
        config: GatewayConfig,
        *,
        client_factory: ClientFactory | None = None,
        trace_sink: TraceSink | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self._client_factory = client_factory or self._create_client
        self._trace_sink = trace_sink
        self._sleep = sleep

    def invoke(self, request: LLMRequest) -> LLMResponse:
        trace_id = str(request.metadata.get("trace_id") or uuid.uuid4())
        started = time.perf_counter()
        retries = 0
        error: Exception | None = None
        client = self._client_factory(request)

        for attempt in range(self.config.max_retries + 1):
            try:
                raw = client.invoke([message.as_dict() for message in request.messages])
                response = self._normalize_response(raw, request, retries, started)
                self._emit(trace_id, request, response=response)
                return response
            except Exception as exc:
                error = exc
                if attempt >= self.config.max_retries or not self._is_retryable(exc):
                    break
                retries += 1
                self._sleep(self.config.retry_backoff_seconds * (2 ** attempt))

        self._emit(trace_id, request, error=error, retries=retries)
        raise ProviderInvocationError(
            f"{request.provider} invocation failed after {retries} retries: {error}"
        ) from error

    def _create_client(self, request: LLMRequest) -> ChatClient:
        provider = request.provider.strip().lower()
        common: dict[str, Any] = {
            "model": request.model,
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
        }
        if provider in {"anthropic", "claude", "minimax-anth"}:
            from langchain_anthropic import ChatAnthropic

            if not self.config.api_key:
                raise ProviderConfigurationError("Anthropic-compatible API key is missing")
            common["api_key"] = self.config.api_key
            if self.config.base_url:
                common["base_url"] = self.config.base_url
            return ChatAnthropic(**common)

        if provider in {"ollama"}:
            from langchain_ollama import ChatOllama

            common.pop("max_tokens", None)
            if self.config.base_url:
                common["base_url"] = self.config.base_url
            return ChatOllama(**common)

        if provider in {
            "openai", "openai_chat", "openai_response", "openai-resp",
            "minimax-chat", "minimax-resp", "deepseek", "moonshot", "qwen",
            "doubao", "yi", "zhipu",
        }:
            from langchain_openai import ChatOpenAI

            if not self.config.api_key and provider != "ollama":
                raise ProviderConfigurationError("OpenAI-compatible API key is missing")
            common["api_key"] = self.config.api_key
            if self.config.base_url:
                common["base_url"] = self.config.base_url
            return ChatOpenAI(**common)

        raise ProviderConfigurationError(f"Unsupported provider: {request.provider}")

    @staticmethod
    def _normalize_response(raw: Any, request: LLMRequest, retries: int, started: float) -> LLMResponse:
        metadata = getattr(raw, "response_metadata", {}) or {}
        usage_data = getattr(raw, "usage_metadata", None) or metadata.get("token_usage") or {}

        def usage_value(*names: str) -> int:
            for name in names:
                value = usage_data.get(name) if isinstance(usage_data, dict) else getattr(usage_data, name, None)
                if value is not None:
                    return int(value)
            return 0

        input_tokens = usage_value("input_tokens", "prompt_tokens")
        output_tokens = usage_value("output_tokens", "completion_tokens")
        total_tokens = usage_value("total_tokens") or input_tokens + output_tokens
        content = getattr(raw, "content", raw)
        if isinstance(content, list):
            content = "".join(
                str(block.get("text", "")) if isinstance(block, dict) else str(block)
                for block in content
            )
        finish_reason = metadata.get("finish_reason") or metadata.get("stop_reason") or ""
        model = metadata.get("model_name") or metadata.get("model") or request.model
        safe_metadata = {
            key: value for key, value in metadata.items()
            if key not in {"api_key", "authorization", "headers", "token_usage"}
        }
        return LLMResponse(
            content=str(content),
            model=str(model),
            provider=request.provider,
            usage=TokenUsage(input_tokens, output_tokens, total_tokens),
            finish_reason=str(finish_reason),
            response_id=str(getattr(raw, "id", "") or ""),
            latency_ms=round((time.perf_counter() - started) * 1000),
            retries=retries,
            raw_metadata=safe_metadata,
        )

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status is not None:
            return status == 429 or status >= 500
        return isinstance(exc, (TimeoutError, ConnectionError))

    def _emit(
        self,
        trace_id: str,
        request: LLMRequest,
        *,
        response: LLMResponse | None = None,
        error: Exception | None = None,
        retries: int = 0,
    ) -> None:
        if self._trace_sink:
            self._trace_sink.record(trace_id, request, response=response, error=error, retries=retries)

