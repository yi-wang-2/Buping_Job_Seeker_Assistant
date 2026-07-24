from __future__ import annotations

from typing import Any

from ..context import ContextManager, TokenBudgetAllocator
from ..models import LLMRequest
from ..optimization import PromptCache
from ..providers import LLMGateway
from .base import SkillResult
from .registry import SkillRegistry


class SkillRunner:
    def __init__(
        self,
        registry: SkillRegistry,
        gateway: LLMGateway,
        context_manager: ContextManager | None = None,
        allocator: TokenBudgetAllocator | None = None,
        cache: PromptCache | None = None,
    ) -> None:
        self.registry = registry
        self.gateway = gateway
        self.context_manager = context_manager or ContextManager()
        self.allocator = allocator or TokenBudgetAllocator()
        self.cache = cache

    def run(
        self,
        skill_name: str,
        inputs: dict[str, Any],
        *,
        provider: str,
        model: str,
        trace_id: str = "",
    ) -> SkillResult:
        skill = self.registry.get(skill_name)
        skill.validate_input(inputs)
        allocation = self.allocator.allocate(skill.metadata.token_budget, skill.metadata.context_weights)
        context = self.context_manager.build(skill.context_items(inputs), allocation)
        messages = skill.build_messages(inputs, context.items)
        context_original_tokens = sum(decision.original_tokens for decision in context.decisions)
        compressed_count = sum(decision.action == "compressed" for decision in context.decisions)
        dropped_count = sum(decision.action == "dropped" for decision in context.decisions)
        request = LLMRequest(
            messages=messages,
            model=model,
            provider=provider,
            max_output_tokens=skill.metadata.token_budget.reserved_output,
            metadata={
                "skill": skill.metadata.name,
                "skill_version": skill.metadata.version,
                "trace_id": trace_id,
                "context_original_tokens": context_original_tokens,
                "context_final_tokens": context.total_tokens,
                "context_items_kept": len(context.items),
                "context_items_compressed": compressed_count,
                "context_items_dropped": dropped_count,
            },
        )
        cache_key = ""
        if self.cache and skill.metadata.cacheable:
            cache_key = self.cache.key(
                provider=provider, model=model, skill=skill.metadata.name,
                skill_version=skill.metadata.version,
                messages=[message.as_dict() for message in messages],
                parameters={"temperature": request.temperature, "max_output_tokens": request.max_output_tokens},
            )
            cached = self.cache.get(cache_key)
            if cached:
                result = skill.parse_output(cached)
                return SkillResult(
                    content=result.content, structured_output=result.structured_output,
                    usage=result.usage, cache_hit=True, memories_used=result.memories_used,
                    warnings=result.warnings, trace_id=result.trace_id,
                )
        response = self.gateway.invoke(request)
        if self.cache and cache_key:
            self.cache.put(cache_key, response)
        return skill.parse_output(response)
