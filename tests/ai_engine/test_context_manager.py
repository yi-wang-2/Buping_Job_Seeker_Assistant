from src.libs.ai_engine.context import (
    BudgetAllocation,
    ContextItem,
    ContextKind,
    ContextManager,
)


def test_context_manager_deduplicates_and_explains_decisions():
    manager = ContextManager()
    items = [
        ContextItem("a", ContextKind.TASK, "Python\n\nPython", "jd", relevance=0.9),
        ContextItem("b", ContextKind.TASK, "Python", "memory", relevance=0.1),
    ]

    bundle = manager.build(items, BudgetAllocation(100, {"task": 100}))

    assert len(bundle.items) == 1
    assert bundle.items[0].content == "Python"
    assert any(decision.reason == "duplicate" for decision in bundle.decisions)


def test_context_manager_respects_section_budget():
    manager = ContextManager()
    items = [ContextItem("a", ContextKind.HISTORY, "one two three four", "chat")]

    bundle = manager.build(items, BudgetAllocation(2, {"history": 2}))

    assert bundle.total_tokens <= 2

