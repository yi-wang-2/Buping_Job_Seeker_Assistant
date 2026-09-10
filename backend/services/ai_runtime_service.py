"""Composition root for the unified AI Runtime.

Business services provide credentials and the Skills they expose; lifecycle,
cache, memory and observability wiring stays consistent here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from src.libs.ai_engine.memory import MemoryManager, SQLiteMemoryRepository
from src.libs.ai_engine.optimization import PromptCache
from src.libs.ai_engine.providers import GatewayConfig, LLMGateway
from src.libs.ai_engine.runtime import AIRuntime
from src.libs.ai_engine.skills import Skill, SkillRegistry


@dataclass(frozen=True, slots=True)
class RuntimeBundle:
    runtime: AIRuntime
    registry: SkillRegistry
    repository: SQLiteMemoryRepository


def build_ai_runtime(
    config: dict[str, str],
    skills: Iterable[Skill],
    *,
    max_retries: int = 2,
    available_tools: set[str] | Mapping[str, Callable[..., Any]] | None = None,
    trace_sink: Any | None = None,
    context_providers: Mapping[str, Any] | None = None,
) -> RuntimeBundle:
    skill_list = list(skills)
    if trace_sink is None:
        # Resolve lazily so tests and deployments can replace the sink centrally.
        from src.libs.ai_engine import observability
        trace_sink = observability.JsonlTraceSink()
    repository = SQLiteMemoryRepository()
    builtin_tools: dict[str, Callable[..., Any]] = {
        "archive_job_description": repository.archive_job_description,
    }
    if isinstance(available_tools, Mapping):
        builtin_tools.update(available_tools)
    elif available_tools is not None:
        builtin_tools = {name: handler for name, handler in builtin_tools.items() if name in available_tools}
    cache = PromptCache(repository.path) if repository.get_setting("cache_enabled", True) else None
    gateway = LLMGateway(
        GatewayConfig(
            api_key=config.get("api_key", ""),
            base_url=config.get("base_url", ""),
            max_retries=max_retries,
        ),
        trace_sink=trace_sink,
    )
    registry = SkillRegistry()
    for skill in skill_list:
        registry.register(skill)
    resolved_context_providers = dict(context_providers or {})
    if any("interview_knowledge" in skill.metadata.context_providers for skill in skill_list):
        try:
            from backend.services.interview_knowledge_service import get_interview_knowledge_service
            from src.libs.ai_engine.knowledge import InterviewKnowledgeRuntimeProvider
            resolved_context_providers.setdefault(
                "interview_knowledge",
                InterviewKnowledgeRuntimeProvider(get_interview_knowledge_service().retriever),
            )
        except Exception:
            # Knowledge augmentation is optional and the Runner records its absence.
            pass
    runtime = AIRuntime(
        gateway,
        registry,
        cache=cache,
        memory_manager=MemoryManager(repository),
        repository=repository,
        available_tools=builtin_tools,
        context_providers=resolved_context_providers,
    )
    return RuntimeBundle(runtime=runtime, registry=registry, repository=repository)
