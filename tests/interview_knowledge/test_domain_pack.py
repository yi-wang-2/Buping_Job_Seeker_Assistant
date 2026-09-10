from src.libs.ai_engine.knowledge import DomainPackRegistry
from src.libs.interview_prep.answer_evaluator import evaluate_answer_signals


def test_ai_agent_domain_pack_adds_specific_and_runtime_competencies():
    metadata = DomainPackRegistry().get("ai_agent").enrich(
        "如何评估 RAG？", "讨论召回、重排序、引用和可观测性。", {},
    )

    assert metadata["topic"] == "RAG"
    assert "ai" in metadata["competencies"]
    assert "评测与可观测" in metadata["competencies"]


def test_answer_signal_only_steers_and_distinguishes_shallow_from_deep_answer():
    shallow = evaluate_answer_signals("不知道")
    deep = evaluate_answer_signals(
        "我负责过这个项目，因为召回率不足，所以增加混合检索。例如固定数据集上命中率提升 12%，"
        "但代价是 P95 延迟增加 20ms，我们在效果和延迟之间做了权衡。"
    )

    assert shallow.decision == "follow_up"
    assert deep.depth > shallow.depth
    assert deep.has_example and deep.has_reasoning and deep.has_tradeoff and deep.has_result
