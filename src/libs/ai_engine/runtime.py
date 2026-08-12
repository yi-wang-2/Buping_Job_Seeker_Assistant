from __future__ import annotations

from typing import Any

from .memory import MemoryManager, SQLiteMemoryRepository
from .providers import LLMGateway
from .optimization import PromptCache
from .skills import SkillRegistry, SkillResult, SkillRunner


class AIRuntime:
    def __init__(
        self,
        gateway: LLMGateway,
        registry: SkillRegistry | None = None,
        cache: PromptCache | None = None,
        *,
        memory_manager: MemoryManager | None = None,
        repository: SQLiteMemoryRepository | None = None,
        available_tools: set[str] | None = None,
    ) -> None:
        self.registry = registry or SkillRegistry()
        self.runner = SkillRunner(
            self.registry, gateway, cache=cache,
            memory_manager=memory_manager, repository=repository,
            available_tools=available_tools,
        )

    def execute(
        self,
        skill_name: str,
        inputs: dict[str, Any],
        *,
        provider: str,
        model: str,
        trace_id: str = "",
        user_id: str = "local",
        session_id: str = "",
    ) -> SkillResult:
        return self.runner.run(
            skill_name, inputs, provider=provider, model=model, trace_id=trace_id,
            user_id=user_id, session_id=session_id,
        )
