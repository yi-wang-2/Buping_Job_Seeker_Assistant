from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


class TokenEstimator(Protocol):
    def count(self, text: str) -> int: ...


class ConservativeTokenEstimator:
    """Dependency-free upper-bound estimate suitable for mixed Chinese/English."""

    _cjk = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
    _word = re.compile(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]")

    def count(self, text: str) -> int:
        if not text:
            return 0
        cjk_count = len(self._cjk.findall(text))
        remainder = self._cjk.sub(" ", text)
        other_units = len(self._word.findall(remainder))
        return max(1, cjk_count + other_units)


@dataclass(frozen=True, slots=True)
class ModelCapability:
    context_window: int
    tokenizer: str = "conservative"


MODEL_CAPABILITIES: dict[str, ModelCapability] = {
    "gpt-4o": ModelCapability(128000, "o200k_base"),
    "gpt-4.1": ModelCapability(1047576, "o200k_base"),
    "gpt-5": ModelCapability(400000, "o200k_base"),
    "claude-3": ModelCapability(200000),
    "claude-sonnet-4": ModelCapability(200000),
    "deepseek-chat": ModelCapability(128000),
    "minimax-m": ModelCapability(204800),
}


class TikTokenEstimator:
    """Exact OpenAI-family tokenizer when optional tiktoken is installed."""

    def __init__(self, encoding_name: str) -> None:
        import tiktoken  # type: ignore[import-not-found]
        self.encoding = tiktoken.get_encoding(encoding_name)

    def count(self, text: str) -> int:
        return len(self.encoding.encode(text)) if text else 0


def model_capability(provider: str, model: str, fallback_limit: int = 32000) -> ModelCapability:
    normalized = f"{provider}:{model}".lower()
    for prefix, capability in MODEL_CAPABILITIES.items():
        if prefix in normalized:
            return capability
    return ModelCapability(fallback_limit)


def token_estimator_for_model(provider: str, model: str) -> TokenEstimator:
    capability = model_capability(provider, model)
    if capability.tokenizer != "conservative":
        try:
            return TikTokenEstimator(capability.tokenizer)
        except (ImportError, KeyError, ValueError):
            pass
    return ConservativeTokenEstimator()

