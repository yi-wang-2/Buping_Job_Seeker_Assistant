"""Production service entry points for unified AI Skills."""

from __future__ import annotations

from typing import Any

from backend.services.config_service import load_secrets, resolve_llm_model
from backend.services.ai_runtime_service import build_ai_runtime
from src.libs.ai_engine.memory import SQLiteMemoryRepository
from src.libs.ai_engine.observability import JsonlTraceSink
from src.libs.ai_engine.skills.builtin import CareerAdvisorSkill, JDAnalyzerSkill, SkillMatcherSkill
from src.libs.ai_engine.skills.factory import create_builtin_registry


def _resolve_config(api_key: str, provider: str, model: str, base_url: str) -> dict[str, str]:
    from backend.services.config_service import PUBLIC_DEMO_MODE
    if PUBLIC_DEMO_MODE and not api_key:
        raise ValueError("Public demo requires your own API key for each AI request.")
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

    skill = JDAnalyzerSkill()
    bundle = build_ai_runtime(config, [skill], trace_sink=JsonlTraceSink())
    result = bundle.runtime.execute(
        skill.metadata.name,
        {"job_description": job_description, "source_url": source_url},
        provider=config["provider"],
        model=config["model"],
    )
    analysis = result.structured_output or {}
    archive = next((item["output"] for item in result.tool_results if item["name"] == "archive_job_description"), {})
    return {
        "analysis": analysis,
        "archive": archive,
        "run_id": result.run_id,
        "cache_hit": result.cache_hit,
        "usage": {
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "total_tokens": result.usage.total_tokens,
        },
    }


def list_archived_jobs(limit: int = 50) -> list[dict[str, Any]]:
    return SQLiteMemoryRepository().list_job_descriptions(limit=limit)


def list_builtin_skills() -> list[dict[str, Any]]:
    return list(create_builtin_registry().describe())


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
    bundle = build_ai_runtime(config, [skill], trace_sink=JsonlTraceSink())
    result = bundle.runtime.execute(
        skill.metadata.name, inputs, provider=config["provider"], model=config["model"],
    )
    usage = {
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        "total_tokens": result.usage.total_tokens,
    }
    return {
        "content": result.content,
        "structured_output": result.structured_output,
        "run_id": result.run_id,
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
