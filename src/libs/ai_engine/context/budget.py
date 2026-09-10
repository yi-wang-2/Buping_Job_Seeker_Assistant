from __future__ import annotations

from dataclasses import dataclass, field

from ..exceptions import ContextBudgetError


DEFAULT_WEIGHTS = {
    "system": 0.10,
    "request": 0.10,
    "task": 0.35,
    "retrieved_knowledge": 0.15,
    "working": 0.15,
    "long_term": 0.10,
    "history": 0.10,
}

DEFAULT_MINIMUMS = {
    "system": 1800,
    "request": 1200,
    "task": 1200,
    "retrieved_knowledge": 600,
    "working": 600,
    "long_term": 300,
    "history": 300,
}


@dataclass(frozen=True, slots=True)
class TokenBudget:
    model_context_limit: int = 32000
    reserved_output: int = 4000
    reserved_system: int = 2000
    safety_margin: int = 1000

    @property
    def available_input(self) -> int:
        available = self.model_context_limit - self.reserved_output - self.safety_margin
        if available <= 0:
            raise ContextBudgetError("Output reservation and safety margin exhaust the context window")
        return available


@dataclass(frozen=True, slots=True)
class BudgetAllocation:
    total_input: int
    sections: dict[str, int] = field(default_factory=dict)
    minimums: dict[str, int] = field(default_factory=dict)


class TokenBudgetAllocator:
    def allocate(
        self,
        budget: TokenBudget,
        weights: dict[str, float] | None = None,
        minimums: dict[str, int] | None = None,
    ) -> BudgetAllocation:
        effective = weights or DEFAULT_WEIGHTS
        if not effective or any(value < 0 for value in effective.values()):
            raise ValueError("Budget weights must be non-negative")
        weight_sum = sum(effective.values())
        if weight_sum <= 0:
            raise ValueError("At least one budget weight must be positive")

        total = budget.available_input
        requested_minimums = {
            name: max(0, int((minimums or DEFAULT_MINIMUMS).get(name, 0)))
            for name in effective
        }
        requested_minimums["system"] = max(
            requested_minimums.get("system", 0), budget.reserved_system,
        )
        minimum_total = sum(requested_minimums.values())
        if minimum_total > total:
            # Scale all minima proportionally, then restore as much of the protected
            # system floor as the actual input window permits.
            scale = total / minimum_total
            resolved_minimums = {
                name: int(value * scale) for name, value in requested_minimums.items()
            }
            resolved_minimums["system"] = min(
                total, max(resolved_minimums.get("system", 0), min(budget.reserved_system, total)),
            )
            overflow = sum(resolved_minimums.values()) - total
            for name in sorted(
                (item for item in resolved_minimums if item != "system"),
                key=resolved_minimums.get,
                reverse=True,
            ):
                reduction = min(overflow, resolved_minimums[name])
                resolved_minimums[name] -= reduction
                overflow -= reduction
                if overflow <= 0:
                    break
        else:
            resolved_minimums = requested_minimums
        flexible = total - sum(resolved_minimums.values())
        sections = {
            name: resolved_minimums[name] + int(flexible * weight / weight_sum)
            for name, weight in effective.items()
        }
        remainder = total - sum(sections.values())
        if remainder:
            highest = max(effective, key=effective.get)
            sections[highest] += remainder
        return BudgetAllocation(total_input=total, sections=sections, minimums=resolved_minimums)

