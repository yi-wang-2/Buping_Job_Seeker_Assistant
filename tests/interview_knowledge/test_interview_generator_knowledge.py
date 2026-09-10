from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.libs.ai_engine.knowledge import InterviewBlueprint, KnowledgeUnit, RetrievalHit, RetrievalResult
from src.libs.interview_prep.interview_generator import InterviewPrepGenerator


class _Runtime:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def execute(self, skill, inputs, **kwargs):
        self.calls.append((skill, inputs, kwargs))
        return self.responses.pop(0)


def _result(content, finish_reason="stop", unit_ids=None):
    return SimpleNamespace(
        content=content, structured_output={"finish_reason": finish_reason},
        context_metadata={"knowledge_unit_ids": list(unit_ids or [])},
    )


def _report(body: str, count: int = 5) -> str:
    return body + "\n" + "\n".join(f"### Q{i}\n- **问题**：题目" for i in range(1, count + 1))


def _augmentation():
    unit = KnowledgeUnit(
        id="known-unit", source_id="source-1", unit_type="question_card",
        title="RAG", content="检索结果需要引用校验。", domain="interview",
        topic="RAG", source_path="knowledge.json#1", content_hash="hash",
        metadata={
            "question": "如何保证 RAG 回答可追溯？",
            "reference_answer": "校验引用与原文。",
            "competencies": ["RAG"],
            "interviewer_intent": "考察 grounding",
        },
    )
    retrieval = RetrievalResult(
        query={"text": "RAG"}, hits=[RetrievalHit(unit=unit, score=.9, reasons=["fts"])],
        total_candidates=1, retrieval_ms=1, index_version="test", as_of=datetime.now(timezone.utc),
    )
    blueprint = InterviewBlueprint(
        target_role="AI 工程师", competency_weights={"RAG": 1.0},
        weak_topics=["RAG"], source_ids=["source-1"],
    )
    return SimpleNamespace(context="外部资料 [K:known-unit]", blueprint=blueprint, retrieval=retrieval)


def _install(monkeypatch, runtime, augmentation):
    import backend.services.ai_runtime_service as runtime_service

    monkeypatch.setattr(runtime_service, "build_ai_runtime", lambda *_args, **_kwargs: SimpleNamespace(runtime=runtime))


def test_generator_retries_once_when_grounded_output_has_no_citation(monkeypatch):
    runtime = _Runtime([
        _result(_report("第一次没有引用"), unit_ids=["known-unit"]),
        _result(_report("已修正 [K:known-unit]"), unit_ids=["known-unit"]),
    ])
    _install(monkeypatch, runtime, _augmentation())

    output = InterviewPrepGenerator(api_key="test").generate("简历", "AI 工程师", "技术面试", 5)

    assert output == _report("已修正 [K:known-unit]")
    assert len(runtime.calls) == 2
    assert runtime.calls[0][1]["resume"] == "简历"
    assert "knowledge_unit_ids" not in runtime.calls[0][1]


def test_generator_rejects_fabricated_citation_after_retry(monkeypatch):
    runtime = _Runtime([
        _result(_report("[K:fake]"), unit_ids=["known-unit"]),
        _result(_report("[K:still-fake]"), unit_ids=["known-unit"]),
    ])
    _install(monkeypatch, runtime, _augmentation())

    with pytest.raises(RuntimeError, match="引用校验"):
        InterviewPrepGenerator(api_key="test").generate("简历", "AI 工程师", "技术面试", 5)


def test_generator_falls_back_when_optional_knowledge_is_unavailable(monkeypatch):
    runtime = _Runtime([_result(_report("普通报告"))])
    _install(monkeypatch, runtime, None)
    output = InterviewPrepGenerator(api_key="test").generate("简历", "AI 工程师", "技术面试", 5)

    assert output == _report("普通报告")
    assert "knowledge_context" not in runtime.calls[0][1]


def test_generator_rejects_truncated_citation_retry(monkeypatch):
    runtime = _Runtime([
        _result(_report("无引用"), unit_ids=["known-unit"]),
        _result(_report("[K:known-unit]"), "length", ["known-unit"]),
    ])
    _install(monkeypatch, runtime, _augmentation())

    with pytest.raises(RuntimeError, match="达到输出长度上限"):
        InterviewPrepGenerator(api_key="test").generate("简历", "AI 工程师", "技术面试", 5)


def test_question_count_harness_retries_and_requires_exact_total(monkeypatch):
    first = "\n".join(f"### Q{i}\n- **问题**：题目" for i in range(1, 5))
    corrected = "\n".join(f"### Q{i}\n- **问题**：题目" for i in range(1, 6))
    runtime = _Runtime([_result(first), _result(corrected)])
    _install(monkeypatch, runtime, None)

    output = InterviewPrepGenerator(api_key="test").generate("简历", "AI 工程师", "技术面试", 5)

    assert output == corrected
    assert len(runtime.calls) == 2


def test_question_count_validator_does_not_double_count_question_body():
    report = "\n".join(
        f"### Q{i}\n- **问题**：第 {i} 题\n- **考察点**：测试" for i in range(1, 4)
    )
    assert InterviewPrepGenerator._valid_question_count(report, 3)
    assert not InterviewPrepGenerator._valid_question_count(report, 4)
