"""Composition root for the unified AI Runtime.

Business services provide credentials and the Skills they expose; lifecycle,
cache, memory and observability wiring stays consistent here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

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
    available_tools: set[str] | None = None,
    trace_sink: Any | None = None,
) -> RuntimeBundle:
    if trace_sink is None:
        # Resolve lazily so tests and deployments can replace the sink centrally.
        from src.libs.ai_engine import observability
        trace_sink = observability.JsonlTraceSink()
    repository = SQLiteMemoryRepository()
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
    for skill in skills:
        registry.register(skill)
    runtime = AIRuntime(
        gateway,
        registry,
        cache=cache,
        memory_manager=MemoryManager(repository),
        repository=repository,
        available_tools=available_tools,
    )
    return RuntimeBundle(runtime=runtime, registry=registry, repository=repository)
