from __future__ import annotations

import json
import uuid
from dataclasses import replace
from typing import Any, Callable, Mapping

from ..context import ContextItem, ContextKind, ContextManager, ContextProviderResult, TokenBudgetAllocator, model_capability, token_estimator_for_model
from ..memory import MemoryManager, SQLiteMemoryRepository
from ..models import LLMRequest, TokenUsage
from ..optimization import PromptCache, document_fingerprint
from ..presentation.service import build_skill_presentation
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
        memory_manager: MemoryManager | None = None,
        repository: SQLiteMemoryRepository | None = None,
        available_tools: set[str] | Mapping[str, Callable[..., Any]] | None = None,
        context_providers: Mapping[str, Any] | None = None,
    ) -> None:
        self.registry = registry
        self.gateway = gateway
        self.context_manager = context_manager or ContextManager()
        self.allocator = allocator or TokenBudgetAllocator()
        self.cache = cache
        self.memory_manager = memory_manager
        self.repository = repository
        self.tool_handlers = dict(available_tools) if isinstance(available_tools, Mapping) else {}
        self.available_tools = frozenset(self.tool_handlers or (available_tools or ()))
        self.context_providers = dict(context_providers or {})

    def run(
        self,
        skill_name: str,
        inputs: dict[str, Any],
        *,
        provider: str,
        model: str,
        trace_id: str = "",
        user_id: str = "local",
        session_id: str = "",
        stream_event_sink: Any | None = None,
    ) -> SkillResult:
        skill = self.registry.get(skill_name)
        metadata = skill.metadata
        if not metadata.enabled:
            raise ValueError(f"Skill is disabled: {skill_name}")
        unavailable_tools = set(metadata.tools) - self.available_tools
        if unavailable_tools:
            raise PermissionError(
                f"Skill '{skill_name}' requested unavailable tools: {', '.join(sorted(unavailable_tools))}"
            )
        trace_id = trace_id or str(uuid.uuid4())
        validated_inputs = self._validate_inputs(skill, inputs)
        input_hash = document_fingerprint(validated_inputs)
        try:
            skill.validate_input(validated_inputs)
            memory_context, memories_used = self._recall_memories(metadata.memory_read, user_id)
            provider_items, provider_metadata, provider_warnings, validated_inputs = self._provide_context(
                metadata.context_providers, metadata.name, validated_inputs, user_id, session_id,
            )
            capability = model_capability(provider, model, metadata.token_budget.model_context_limit)
            effective_budget = replace(
                metadata.token_budget,
                model_context_limit=min(metadata.token_budget.model_context_limit, capability.context_window),
            )
            allocation = self.allocator.allocate(
                effective_budget, metadata.context_weights, metadata.context_minimums,
            )
            context = self.context_manager.build(
                [*skill.context_items(validated_inputs), *provider_items, *memory_context], allocation,
                estimator=token_estimator_for_model(provider, model) if self.context_manager.model_aware else None,
            )
            messages = skill.build_messages(validated_inputs, context.items)
        except Exception as exc:
            self._record_run(metadata.name, metadata.version, input_hash, model, TokenUsage(), False,
                             "error", type(exc).__name__, user_id, session_id)
            raise
        context_original_tokens = sum(decision.original_tokens for decision in context.decisions)
        compressed_count = sum(decision.action == "compressed" for decision in context.decisions)
        dropped_count = sum(decision.action == "dropped" for decision in context.decisions)
        request = LLMRequest(
            messages=messages,
            model=model,
            provider=provider,
            temperature=metadata.temperature,
            max_output_tokens=metadata.token_budget.reserved_output,
            timeout_seconds=metadata.timeout_seconds,
            metadata={
                "skill": metadata.name,
                "skill_version": metadata.version,
                "prompt_version": metadata.prompt_version,
                "schema_version": metadata.schema_version,
                "trace_id": trace_id,
                "context_original_tokens": context_original_tokens,
                "context_final_tokens": context.total_tokens,
                "context_items_kept": len(context.items),
                "context_items_compressed": compressed_count,
                "context_items_dropped": dropped_count,
                "model_context_limit": capability.context_window,
                "tokenizer": capability.tokenizer,
                **provider_metadata,
            },
            stream_event_sink=stream_event_sink,
        )
        cache_key = ""
        if self.cache and metadata.cacheable:
            cache_key = self.cache.key(
                provider=provider, model=model, skill=metadata.name,
                skill_version=f"{metadata.version}:prompt-{metadata.prompt_version}",
                messages=[message.as_dict() for message in messages],
                parameters={"temperature": request.temperature, "max_output_tokens": request.max_output_tokens},
                schema_version=metadata.schema_version,
            )
            cached = self.cache.get(cache_key)
            if cached:
                try:
                    result = self._validate_output(skill, skill.parse_output(cached), validated_inputs)
                    result = replace(
                        result,
                        usage=TokenUsage(),
                        cached_usage=cached.usage,
                        cache_hit=True,
                        memories_used=tuple(dict.fromkeys((*memories_used, *result.memories_used))),
                        trace_id=trace_id,
                        warnings=tuple(dict.fromkeys((*provider_warnings, *result.warnings))),
                        context_metadata=provider_metadata,
                    )
                    result = self._collect_memory_writes(skill, result, validated_inputs)
                    result = self._write_memories(metadata.memory_write, result, user_id)
                    result = self._execute_tools(skill, result, validated_inputs)
                    run_id = self._record_run(metadata.name, metadata.version, input_hash, model, result.usage, True,
                                              "success", "", user_id, session_id)
                    return replace(result, run_id=run_id)
                except Exception as exc:
                    # Never let a malformed historical response poison future calls.
                    self.cache.delete(cache_key)
        response = None
        try:
            response = self.gateway.invoke(request)
            result = self._validate_output(skill, skill.parse_output(response), validated_inputs)
            if self.cache and cache_key:
                self.cache.put(cache_key, response, ttl_seconds=metadata.cache_ttl_seconds)
            result = replace(
                result,
                memories_used=tuple(dict.fromkeys((*memories_used, *result.memories_used))),
                trace_id=trace_id,
                warnings=tuple(dict.fromkeys((*provider_warnings, *result.warnings))),
                context_metadata=provider_metadata,
            )
            result = self._collect_memory_writes(skill, result, validated_inputs)
            result = self._write_memories(metadata.memory_write, result, user_id)
            result = self._execute_tools(skill, result, validated_inputs)
            run_id = self._record_run(metadata.name, metadata.version, input_hash, model, result.usage, False,
                                      "success", "", user_id, session_id)
            return replace(result, run_id=run_id)
        except Exception as exc:
            failure_usage = response.usage if response is not None else TokenUsage()
            try:
                setattr(exc, "skill_usage", failure_usage)
            except Exception:
                pass
            self._record_run(metadata.name, metadata.version, input_hash, model, failure_usage, False,
                             "error", type(exc).__name__, user_id, session_id)
            raise

    def _provide_context(
        self, names: tuple[str, ...], skill_name: str, inputs: dict[str, Any],
        user_id: str, session_id: str,
    ) -> tuple[list[ContextItem], dict[str, Any], tuple[str, ...], dict[str, Any]]:
        items: list[ContextItem] = []
        metadata: dict[str, Any] = {}
        warnings: list[str] = []
        enriched = dict(inputs)
        for name in names:
            provider = self.context_providers.get(name)
            if provider is None:
                warnings.append(f"Optional context provider is unavailable: {name}")
                continue
            result = provider.provide(
                skill_name=skill_name, inputs=dict(enriched), user_id=user_id,
                session_id=session_id or None,
            )
            if not isinstance(result, ContextProviderResult):
                raise TypeError(f"Context provider '{name}' returned an invalid result")
            for key, value in result.input_updates.items():
                current = enriched.get(key)
                if current not in (None, "", [], {}) and current != value:
                    raise ValueError(f"Context provider '{name}' cannot overwrite input: {key}")
                enriched[key] = value
            items.extend(result.items)
            metadata.update(result.metadata)
            warnings.extend(result.warnings)
        return items, metadata, tuple(dict.fromkeys(warnings)), enriched

    @staticmethod
    def _validate_inputs(skill: Any, inputs: dict[str, Any]) -> dict[str, Any]:
        schema = skill.metadata.input_schema
        if schema is None:
            return dict(inputs)
        validated = schema.model_validate(inputs)
        return validated.model_dump()

    def _execute_tools(self, skill: Any, result: SkillResult, inputs: dict[str, Any]) -> SkillResult:
        builder = getattr(skill, "build_tool_calls", None)
        if not callable(builder):
            return result
        calls = tuple(builder(result, inputs) or ())
        outputs: list[dict[str, Any]] = []
        for call in calls:
            if call.name not in skill.metadata.tools:
                raise PermissionError(f"Skill requested undeclared tool: {call.name}")
            handler = self.tool_handlers.get(call.name)
            if not handler:
                raise PermissionError(f"Tool handler is unavailable: {call.name}")
            outputs.append({"name": call.name, "output": handler(**call.arguments)})
        return replace(result, tool_results=tuple(outputs))

    @staticmethod
    def _validate_output(skill: Any, result: SkillResult, inputs: dict[str, Any]) -> SkillResult:
        schema = skill.metadata.output_schema
        if schema is not None:
            if result.structured_output is None:
                raise ValueError(f"Skill '{skill.metadata.name}' did not return structured output")
            validated = schema.model_validate(result.structured_output)
            result = replace(result, structured_output=validated.model_dump())
        validator = getattr(skill, "validate_output", None)
        if callable(validator):
            validator(result, inputs)
        presentation = build_skill_presentation(skill, result, inputs)
        if presentation is not None:
            result = replace(result, presentation=presentation)
        return result

    def _recall_memories(self, namespaces: tuple[str, ...], user_id: str) -> tuple[list[ContextItem], tuple[str, ...]]:
        if not self.memory_manager:
            return [], ()
        context: list[ContextItem] = []
        used: list[str] = []
        for namespace in namespaces:
            for item in self.memory_manager.recall(user_id, namespace):
                value = item.value if isinstance(item.value, str) else json.dumps(item.value, ensure_ascii=False)
                memory_id = item.id or f"{item.namespace}:{item.key}"
                context.append(ContextItem(
                    id=f"memory-{memory_id}", kind=ContextKind.LONG_TERM,
                    content=f"{item.namespace}.{item.key}: {value}", source="memory",
                    priority=item.importance, relevance=max(0.1, min(1.0, item.confidence)),
                    reliability=max(0.1, min(1.0, item.confidence)),
                    created_at=item.updated_at, expires_at=item.expires_at,
                    metadata={"memory_id": memory_id, "namespace": item.namespace},
                ))
                used.append(memory_id)
        return context, tuple(used)

    @staticmethod
    def _collect_memory_writes(skill: Any, result: SkillResult, inputs: dict[str, Any]) -> SkillResult:
        extractor = getattr(skill, "extract_memories", None)
        if not callable(extractor):
            return result
        candidates = tuple(extractor(result, inputs) or ())
        return replace(result, memory_writes=tuple((*result.memory_writes, *candidates)))

    def _write_memories(self, allowed_namespaces: tuple[str, ...], result: SkillResult, user_id: str) -> SkillResult:
        if not result.memory_writes:
            return result
        if not self.memory_manager:
            return replace(result, warnings=(*result.warnings, "Memory writes were skipped: memory manager unavailable"))
        written: list[str] = []
        for item in result.memory_writes:
            if item.namespace not in allowed_namespaces:
                raise PermissionError(
                    f"Skill memory write is not allowed for namespace: {item.namespace}"
                )
            saved = self.memory_manager.remember(replace(item, user_id=user_id))
            if saved:
                written.append(saved.id or f"{saved.namespace}:{saved.key}")
        return replace(result, memories_used=tuple(dict.fromkeys((*result.memories_used, *written))))

    def _record_run(
        self, skill_name: str, skill_version: str, input_hash: str, model: str,
        usage: TokenUsage, cache_hit: bool, status: str, error_code: str,
        user_id: str, session_id: str,
    ) -> str:
        if not self.repository:
            return ""
        try:
            return self.repository.record_skill_run(
                skill_name=skill_name, skill_version=skill_version,
                input_hash=input_hash, model=model,
                usage={
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                },
                cache_hit=cache_hit, status=status, error_code=error_code,
                user_id=user_id, session_id=session_id,
            )
        except Exception:
            # Observability must never turn a successful model response into a failed request.
            return ""
