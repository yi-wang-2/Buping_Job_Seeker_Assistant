"""Production service entry points for unified AI Skills."""

from __future__ import annotations

from typing import Any

from backend.services.config_service import load_secrets, resolve_llm_model
from src.libs.ai_engine.memory import SQLiteMemoryRepository
from src.libs.ai_engine.observability import JsonlTraceSink
from src.libs.ai_engine.optimization import PromptCache, document_fingerprint
from src.libs.ai_engine.providers import GatewayConfig, LLMGateway
from src.libs.ai_engine.runtime import AIRuntime
from src.libs.ai_engine.skills import SkillRegistry
from src.libs.ai_engine.skills.builtin import CareerAdvisorSkill, JDAnalyzerSkill, SkillMatcherSkill


def _resolve_config(api_key: str, provider: str, model: str, base_url: str) -> dict[str, str]:
    secrets = load_secrets()
    effective_provider = provider or str(secrets.get("llm_model_type", "anthropic"))
    effective_key = api_key or str(secrets.get("llm_api_key", ""))
    effective_model = resolve_llm_model(
        effective_provider,
        model_name=model,
        saved_model=str(secrets.get("llm_model", "")),
        saved_provider=str(secrets.get("llm_model_provider", "")),
    )
    return {
        "api_key": effective_key,
        "provider": effective_provider,
        "model": effective_model,
        "base_url": base_url or str(secrets.get("llm_base_url", "")),
    }


def analyze_job_description(
    job_description: str,
    *,
    api_key: str = "",
    provider: str = "",
    model: str = "",
    base_url: str = "",
    source_url: str = "",
) -> dict[str, Any]:
    if not job_description.strip():
        raise ValueError("Job description cannot be empty")
    config = _resolve_config(api_key, provider, model, base_url)
    if not config["api_key"] and config["provider"].lower() != "ollama":
        raise ValueError("API key is required")

    repository = SQLiteMemoryRepository()
    cache = PromptCache(repository.path) if repository.get_setting("cache_enabled", True) else None
    gateway = LLMGateway(
        GatewayConfig(api_key=config["api_key"], base_url=config["base_url"], max_retries=2),
        trace_sink=JsonlTraceSink(),
    )
    registry = SkillRegistry()
    skill = JDAnalyzerSkill()
    registry.register(skill)
    result = AIRuntime(gateway, registry, cache=cache).execute(
        skill.metadata.name,
        {"job_description": job_description},
        provider=config["provider"],
        model=config["model"],
    )
    analysis = result.structured_output or {}
    archive = repository.archive_job_description(
        job_description,
        analysis,
        company=str(analysis.get("company") or ""),
        role=str(analysis.get("role") or ""),
        source_url=source_url,
    )
    run_id = repository.record_skill_run(
        skill_name=skill.metadata.name,
        skill_version=skill.metadata.version,
        input_hash=document_fingerprint(job_description),
        model=config["model"],
        usage={
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "total_tokens": result.usage.total_tokens,
        },
        cache_hit=result.cache_hit,
    )
    return {
        "analysis": analysis,
        "archive": archive,
        "run_id": run_id,
        "cache_hit": result.cache_hit,
        "usage": {
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "total_tokens": result.usage.total_tokens,
        },
    }


def list_archived_jobs(limit: int = 50) -> list[dict[str, Any]]:
    return SQLiteMemoryRepository().list_job_descriptions(limit=limit)


def _run_text_skill(
    skill: Any,
    inputs: dict[str, Any],
    *,
    api_key: str = "",
    provider: str = "",
    model: str = "",
    base_url: str = "",
) -> dict[str, Any]:
    config = _resolve_config(api_key, provider, model, base_url)
    if not config["api_key"] and config["provider"].lower() != "ollama":
        raise ValueError("API key is required")
    repository = SQLiteMemoryRepository()
    cache = PromptCache(repository.path) if repository.get_setting("cache_enabled", True) else None
    gateway = LLMGateway(
        GatewayConfig(api_key=config["api_key"], base_url=config["base_url"], max_retries=2),
        trace_sink=JsonlTraceSink(),
    )
    registry = SkillRegistry()
    registry.register(skill)
    result = AIRuntime(gateway, registry, cache=cache).execute(
        skill.metadata.name, inputs, provider=config["provider"], model=config["model"],
    )
    source = "\n".join(str(inputs.get(name, "")) for name in sorted(inputs))
    usage = {
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        "total_tokens": result.usage.total_tokens,
    }
    run_id = repository.record_skill_run(
        skill_name=skill.metadata.name,
        skill_version=skill.metadata.version,
        input_hash=document_fingerprint(source),
        model=config["model"],
        usage=usage,
        cache_hit=result.cache_hit,
    )
    return {
        "content": result.content,
        "structured_output": result.structured_output,
        "run_id": run_id,
        "cache_hit": result.cache_hit,
        "usage": usage,
    }


def match_skills(resume: str, job_description: str, **config: str) -> dict[str, Any]:
    return _run_text_skill(
        SkillMatcherSkill(), {"resume": resume, "job_description": job_description}, **config,
    )


def advise_career(
    resume: str,
    *,
    preferences: str = "",
    goals: str = "",
    history: str = "",
    **config: str,
) -> dict[str, Any]:
    return _run_text_skill(
        CareerAdvisorSkill(),
        {"resume": resume, "preferences": preferences, "goals": goals, "history": history},
        **config,
    )
