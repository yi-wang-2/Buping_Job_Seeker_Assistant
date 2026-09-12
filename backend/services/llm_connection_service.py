"""LLM connectivity checks and user-facing failure diagnostics."""

from __future__ import annotations

import time
from typing import Any

from src.libs.ai_engine.models import LLMRequest, Message
from src.libs.ai_engine.providers import GatewayConfig, LLMGateway


def _exception_chain(exc: BaseException) -> str:
    parts: list[str] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).strip()
        if text:
            parts.append(text)
        current = current.__cause__ or current.__context__
    return " | ".join(parts)


def diagnose_llm_error(exc: BaseException) -> tuple[str, str]:
    """Return a stable error code and an actionable, credential-safe message."""
    detail = _exception_chain(exc)
    lowered = detail.lower()
    if any(marker in lowered for marker in ("api key", "authentication", "unauthorized", "401", "403")):
        return "authentication_failed", "模型服务拒绝认证，请检查 API 密钥是否正确、有效且拥有该模型权限。"
    if any(marker in lowered for marker in ("model_not_found", "model not found", "unknown model", "404")):
        return "model_not_found", "模型不存在或当前账号无权使用，请检查模型 ID 与所选服务是否匹配。"
    if any(marker in lowered for marker in ("rate limit", "rate_limit", "429", "too many requests")):
        return "rate_limited", "模型服务当前限流，请稍后重试或检查账户额度。"
    if any(marker in lowered for marker in ("timeout", "timed out")):
        return "connection_timeout", "连接模型服务超时，请检查 API 地址、网络、代理和防火墙设置。"
    if any(marker in lowered for marker in ("connection", "connecterror", "network", "dns", "name resolution")):
        return "connection_failed", "无法连接模型服务，请检查 API 地址以及运行本应用的后端进程是否可以访问网络；如需代理，代理必须对后端进程生效。"
    return "provider_error", f"模型调用失败：{detail[:500] or type(exc).__name__}"


def test_llm_connection(*, api_key: str, provider: str, model: str, base_url: str) -> dict[str, Any]:
    provider = (provider or "").strip()
    model = (model or "").strip()
    base_url = (base_url or "").strip().rstrip("/")
    if not provider:
        raise ValueError("请选择 LLM 服务")
    if not model:
        raise ValueError("请输入模型 ID")
    if provider.lower() != "ollama" and not api_key.strip():
        raise ValueError("请输入 API 密钥")

    started = time.perf_counter()
    gateway = LLMGateway(GatewayConfig(
        api_key=api_key.strip(), base_url=base_url, max_retries=1, retry_backoff_seconds=0.15,
    ))
    response = gateway.invoke(LLMRequest(
        messages=(
            Message("system", "This is a connection test. Reply with OK only."),
            Message("user", "OK"),
        ),
        model=model,
        provider=provider,
        temperature=0,
        max_output_tokens=8,
        timeout_seconds=15,
        metadata={"skill": "connection_test"},
    ))
    return {
        "success": True,
        "provider": provider,
        "model": response.model or model,
        "base_url": base_url,
        "latency_ms": response.latency_ms or round((time.perf_counter() - started) * 1000),
    }
