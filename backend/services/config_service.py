"""Configuration service — reads/writes secrets.yaml and resume content."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import yaml

DATA_FOLDER = Path("data_folder")

DEFAULT_LLM_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "minimax-anth": "MiniMax-M3",
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "zhipu": "glm-4-flash",
    "moonshot": "moonshot-v1-8k",
    "qwen": "qwen-plus",
    "yi": "yi-lightning",
    "minimax-chat": "MiniMax-M3",
    "openai-resp": "gpt-4o-mini",
    "minimax-resp": "MiniMax-M3",
}


def resolve_llm_model(
    model_type: str, model_name: str = "", saved_model: str = "", saved_provider: str = ""
) -> str:
    """Resolve a model without leaking a model from a different provider."""
    if model_name.strip():
        return model_name.strip()
    provider = (model_type or "").strip().lower()
    if saved_model.strip() and saved_provider.strip().lower() == provider:
        return saved_model.strip()
    provider_default = DEFAULT_LLM_MODELS.get(provider)
    if provider_default:
        return provider_default
    raise ValueError("Model ID is required for this provider. Configure it in Settings.")


def load_secrets() -> dict[str, Any]:
    """Load secrets from data_folder/secrets.yaml."""
    secrets_path = DATA_FOLDER / "secrets.yaml"
    if secrets_path.exists():
        with open(secrets_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_secrets(data: dict[str, Any]) -> None:
    """Merge and save data into secrets.yaml."""
    secrets_path = DATA_FOLDER / "secrets.yaml"
    existing: dict[str, Any] = {}
    if secrets_path.exists():
        with open(secrets_path, "r", encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
    existing.update(data)
    with open(secrets_path, "w", encoding="utf-8") as f:
        yaml.dump(existing, f, allow_unicode=True)


async def discover_llm_models(api_key: str, base_url: str, protocol: str) -> list[str]:
    """Best-effort model discovery for OpenAI/Anthropic-compatible APIs."""
    if not api_key.strip() or not base_url.strip():
        return []

    import httpx

    parsed = urlparse(base_url.strip().rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return []
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/responses", "/messages"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    if protocol == "anthropic" and not path.endswith("/v1"):
        path = f"{path}/v1"
    models_url = urlunparse((parsed.scheme, parsed.netloc, f"{path}/models", "", "", ""))
    headers = (
        {"x-api-key": api_key.strip(), "anthropic-version": "2023-06-01", "accept": "application/json"}
        if protocol == "anthropic"
        else {"Authorization": f"Bearer {api_key.strip()}", "accept": "application/json"}
    )
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            response = await client.get(models_url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        return []
    items = payload.get("data", payload.get("models", [])) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return []
    model_ids = {
        str(item if isinstance(item, str) else item.get("id") or item.get("name") or "").strip()
        for item in items if isinstance(item, (str, dict))
    }
    return sorted(model_id for model_id in model_ids if model_id)


def load_resume_content(language: str = "zh") -> str:
    """Load resume YAML content by language."""
    filename = "plain_text_resume.yaml" if language == "en" else "plain_text_resume_zh.yaml"
    filepath = DATA_FOLDER / filename
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def save_resume_content(content: str, language: str = "zh") -> None:
    """Save resume YAML content by language."""
    filename = "plain_text_resume.yaml" if language == "en" else "plain_text_resume_zh.yaml"
    filepath = DATA_FOLDER / filename
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    # Resume history is local and follows the same privacy switch as AI memory.
    try:
        from src.libs.ai_engine.memory import SQLiteMemoryRepository

        repository = SQLiteMemoryRepository()
        if repository.get_setting("memory_enabled", True):
            repository.save_resume_version(
                content,
                language=language,
                change_summary="用户保存简历内容",
            )
    except Exception:
        # Saving the primary resume must not fail because optional history is unavailable.
        pass
