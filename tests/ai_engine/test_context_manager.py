from src.libs.ai_engine.context import (
    BudgetAllocation,
    ContextItem,
    ContextKind,
    ContextManager,
    model_capability,
    token_estimator_for_model,
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


def test_model_capability_and_tokenizer_have_safe_fallbacks():
    assert model_capability("openai", "gpt-4o-mini").context_window == 128000
    assert model_capability("custom", "unknown", 24000).context_window == 24000
    assert token_estimator_for_model("custom", "unknown").count("中文 token test") > 0


def test_context_manager_borrows_unused_section_budget():
    manager = ContextManager()
    items = [ContextItem("task", ContextKind.TASK, "one two three four", "job", relevance=.9)]
    allocation = BudgetAllocation(8, {"task": 2, "history": 6}, {"task": 2, "history": 2})

    bundle = manager.build(items, allocation)

    assert bundle.items[0].content == "one two three four"
    assert any(decision.reason == "borrowed_elastic_budget" for decision in bundle.decisions)


def test_protected_context_uses_global_budget_not_section_cap():
    manager = ContextManager()
    items = [ContextItem(
        "request", ContextKind.REQUEST, "one two three four", "user", protected=True,
    )]

    bundle = manager.build(items, BudgetAllocation(6, {"request": 1, "task": 5}))

    assert bundle.items[0].content == "one two three four"
    assert bundle.decisions[0].reason == "protected_global_budget"

