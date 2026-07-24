import pytest

from src.libs.ai_engine.context import TokenBudget, TokenBudgetAllocator
from src.libs.ai_engine.exceptions import ContextBudgetError


def test_allocator_uses_entire_input_budget():
    allocation = TokenBudgetAllocator().allocate(TokenBudget())

    assert allocation.total_input == 27000
    assert sum(allocation.sections.values()) == 27000
    assert allocation.sections["system"] >= 2000


def test_invalid_budget_fails():
    with pytest.raises(ContextBudgetError):
        TokenBudget(model_context_limit=1000, reserved_output=900, safety_margin=100).available_input

