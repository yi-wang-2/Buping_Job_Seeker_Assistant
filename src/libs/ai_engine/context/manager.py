from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable

from ..exceptions import ContextBudgetError
from .budget import BudgetAllocation
from .compressors import deduplicate_blocks, truncate_semantic_blocks
from .tokenizer import ConservativeTokenEstimator, TokenEstimator


class ContextKind(str, Enum):
    SYSTEM = "system"
    REQUEST = "request"
    TASK = "task"
    RETRIEVED = "retrieved_knowledge"
    WORKING = "working"
    LONG_TERM = "long_term"
    HISTORY = "history"


@dataclass(frozen=True, slots=True)
class ContextItem:
    id: str
    kind: ContextKind
    content: str
    source: str
    priority: int = 50
    relevance: float = 0.5
    reliability: float = 1.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    protected: bool = False
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def score(self, now: datetime | None = None) -> float:
        current = now or datetime.now(timezone.utc)
        age_days = max(0.0, (current - self.created_at).total_seconds() / 86400)
        recency = 1 / (1 + age_days / 30)
        return self.relevance * 0.45 + (self.priority / 100) * 0.25 + recency * 0.15 + self.reliability * 0.15


@dataclass(frozen=True, slots=True)
class ContextDecision:
    item_id: str
    action: str
    reason: str
    original_tokens: int
    final_tokens: int


@dataclass(frozen=True, slots=True)
class ContextBundle:
    items: tuple[ContextItem, ...]
    total_tokens: int
    decisions: tuple[ContextDecision, ...]


@dataclass(frozen=True, slots=True)
class ContextProviderResult:
    """A pre-LLM contribution produced by a Runtime context provider."""

    items: tuple[ContextItem, ...] = ()
    input_updates: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


class ContextManager:
    def __init__(self, estimator: TokenEstimator | None = None) -> None:
        self.estimator = estimator or ConservativeTokenEstimator()
        self.model_aware = estimator is None

    def build(self, items: Iterable[ContextItem], allocation: BudgetAllocation,
              estimator: TokenEstimator | None = None) -> ContextBundle:
        counter = estimator or self.estimator
        now = datetime.now(timezone.utc)
        active = [item for item in items if not item.expires_at or item.expires_at > now]
        unique: dict[tuple[ContextKind, str], ContextItem] = {}
        decisions: list[ContextDecision] = []
        for item in active:
            cleaned = deduplicate_blocks(item.content)
            tokens = counter.count(cleaned)
            normalized = replace(item, content=cleaned, token_count=tokens)
            key = (item.kind, cleaned.casefold())
            existing = unique.get(key)
            if existing and existing.score(now) >= normalized.score(now):
                decisions.append(ContextDecision(item.id, "dropped", "duplicate", tokens, 0))
                continue
            if existing:
                decisions.append(ContextDecision(existing.id, "dropped", "duplicate", existing.token_count, 0))
            unique[key] = normalized

        selected: list[ContextItem] = []
        by_kind: dict[ContextKind, list[ContextItem]] = {}
        for item in unique.values():
            by_kind.setdefault(item.kind, []).append(item)

        protected = sorted(
            (item for values in by_kind.values() for item in values if item.protected),
            key=lambda value: value.score(now), reverse=True,
        )
        protected_tokens = sum(item.token_count for item in protected)
        if protected_tokens > allocation.total_input:
            raise ContextBudgetError(
                f"Protected context requires {protected_tokens} tokens but the request budget is "
                f"{allocation.total_input}"
            )
        selected.extend(protected)
        for item in protected:
            decisions.append(ContextDecision(
                item.id, "kept", "protected_global_budget", item.token_count, item.token_count,
            ))

        used_by_kind = {
            kind: sum(item.token_count for item in protected if item.kind == kind)
            for kind in ContextKind
        }
        total_used = protected_tokens
        overflow: list[ContextItem] = []
        for kind, candidates in by_kind.items():
            section_target = allocation.sections.get(kind.value, 0)
            section_used = used_by_kind.get(kind, 0)
            for item in sorted(
                (value for value in candidates if not value.protected),
                key=lambda value: value.score(now), reverse=True,
            ):
                if (
                    section_used + item.token_count <= section_target
                    and total_used + item.token_count <= allocation.total_input
                ):
                    selected.append(item)
                    section_used += item.token_count
                    total_used += item.token_count
                    decisions.append(ContextDecision(
                        item.id, "kept", "section_guarantee", item.token_count, item.token_count,
                    ))
                else:
                    overflow.append(item)
            used_by_kind[kind] = section_used

        # Any unused section allocation becomes a shared elastic pool. Overflow
        # competes globally by relevance/priority, so low-value context degrades first.
        for item in sorted(overflow, key=lambda value: value.score(now), reverse=True):
            remaining = allocation.total_input - total_used
            if remaining <= 0:
                decisions.append(ContextDecision(
                    item.id, "dropped", "global_budget_exhausted", item.token_count, 0,
                ))
                continue
            if item.token_count <= remaining:
                selected.append(item)
                total_used += item.token_count
                decisions.append(ContextDecision(
                    item.id, "kept", "borrowed_elastic_budget", item.token_count, item.token_count,
                ))
                continue
            compressed = truncate_semantic_blocks(item.content, remaining, counter.count)
            compressed_tokens = counter.count(compressed)
            if compressed and compressed_tokens <= remaining:
                selected.append(replace(item, content=compressed, token_count=compressed_tokens))
                total_used += compressed_tokens
                decisions.append(ContextDecision(
                    item.id, "compressed", "priority_degradation", item.token_count, compressed_tokens,
                ))
            else:
                decisions.append(ContextDecision(
                    item.id, "dropped", "global_budget_exhausted", item.token_count, 0,
                ))

        selected.sort(key=lambda item: list(ContextKind).index(item.kind))
        return ContextBundle(tuple(selected), sum(item.token_count for item in selected), tuple(decisions))
