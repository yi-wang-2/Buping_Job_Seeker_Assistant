from __future__ import annotations

from typing import Any

from .providers import LLMGateway
from .optimization import PromptCache
from .skills import SkillRegistry, SkillResult, SkillRunner


class AIRuntime:
    def __init__(self, gateway: LLMGateway, registry: SkillRegistry | None = None, cache: PromptCache | None = None) -> None:
        self.registry = registry or SkillRegistry()
        self.runner = SkillRunner(self.registry, gateway, cache=cache)

    def execute(
        self,
        skill_name: str,
        inputs: dict[str, Any],
        *,
        provider: str,
        model: str,
        trace_id: str = "",
    ) -> SkillResult:
        return self.runner.run(skill_name, inputs, provider=provider, model=model, trace_id=trace_id)
