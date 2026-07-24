from __future__ import annotations

from dataclasses import dataclass, field

from ..exceptions import ContextBudgetError


DEFAULT_WEIGHTS = {
    "system": 0.10,
    "request": 0.10,
    "task": 0.35,
    "working": 0.20,
    "long_term": 0.15,
    "history": 0.10,
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


class TokenBudgetAllocator:
    def allocate(
        self,
        budget: TokenBudget,
        weights: dict[str, float] | None = None,
    ) -> BudgetAllocation:
        effective = weights or DEFAULT_WEIGHTS
        if not effective or any(value < 0 for value in effective.values()):
            raise ValueError("Budget weights must be non-negative")
        weight_sum = sum(effective.values())
        if weight_sum <= 0:
            raise ValueError("At least one budget weight must be positive")

        total = budget.available_input
        sections = {name: int(total * weight / weight_sum) for name, weight in effective.items()}
        remainder = total - sum(sections.values())
        if remainder:
            highest = max(effective, key=effective.get)
            sections[highest] += remainder
        if sections.get("system", 0) < budget.reserved_system:
            deficit = budget.reserved_system - sections.get("system", 0)
            donors = sorted((name for name in sections if name != "system"), key=sections.get, reverse=True)
            for donor in donors:
                transferable = min(deficit, sections[donor])
                sections[donor] -= transferable
                sections["system"] = sections.get("system", 0) + transferable
                deficit -= transferable
                if deficit == 0:
                    break
            if deficit:
                raise ContextBudgetError("Reserved system context cannot fit in input budget")
        return BudgetAllocation(total_input=total, sections=sections)

