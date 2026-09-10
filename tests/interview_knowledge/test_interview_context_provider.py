from datetime import datetime, timezone

from src.libs.ai_engine.knowledge import (
    HashingEmbeddingProvider,
    HybridKnowledgeRetriever,
    InterviewKnowledgeContextProvider,
    InterviewKnowledgeRuntimeProvider,
    KnowledgeSource,
    KnowledgeUnit,
    SQLiteKnowledgeRepository,
    SQLiteVectorIndex,
)
from src.libs.ai_engine.skills.builtin import InterviewCoachSkill


def _provider(tmp_path):
    repository = SQLiteKnowledgeRepository(tmp_path / "knowledge.sqlite3")
    repository.upsert_source(KnowledgeSource(
        id="public", name="公共知识", source_type="json", location="questions.json",
        license="MIT", created_at=datetime.now(timezone.utc),
    ))
    unit = KnowledgeUnit(
        id="rag-grounding", source_id="public", unit_type="question_card",
        title="RAG 如何降低幻觉？", content="检索后需要重排，并验证引用与原文一致。",
        domain="interview", topic="RAG", roles=["AI Agent 工程师"],
        source_path="questions.json#rag", content_hash="rag-hash", quality_score=.9,
        metadata={
            "question": "RAG 如何降低幻觉？", "reference_answer": "检索和引用校验",
            "competencies": ["RAG"], "interviewer_intent": "考察 grounding",
        },
    )
    repository.sync_units("public", [unit])
    vector = SQLiteVectorIndex(repository, HashingEmbeddingProvider(128))
    vector.index_units([unit])
    return InterviewKnowledgeContextProvider(HybridKnowledgeRetriever(repository, vector))


def test_blueprint_and_retrieval_keep_external_knowledge_separate(tmp_path):
    augmentation = _provider(tmp_path).prepare(
        resume="项目：实现了一个 Agent 工作流。",
        job_description="AI Agent 工程师\n负责 RAG、评测和系统可靠性。",
        interview_type="技术面试",
    )

    assert abs(sum(augmentation.blueprint.competency_weights.values()) - 1) < .001
    assert augmentation.blueprint.target_role == "AI Agent 工程师"
    assert augmentation.blueprint.source_ids == ["public"]
    assert "[K:rag-grounding]" in augmentation.context
    assert "不是候选人的经历" in augmentation.context


def test_interview_skill_budgets_retrieved_knowledge_as_untrusted_task_context(tmp_path):
    runtime_provider = InterviewKnowledgeRuntimeProvider(_provider(tmp_path).retriever)
    skill = InterviewCoachSkill()
    inputs = {
        "resume": "Agent 项目", "job_description": "AI Agent 工程师 RAG",
        "interview_type": "技术面试", "prepared_prompt": "根据简历和 JD 生成报告",
    }
    contribution = runtime_provider.provide(
        skill_name="interview_coach", inputs=inputs, user_id="local", session_id=None,
    )
    items = [*skill.context_items(inputs), *contribution.items]

    knowledge = next(item for item in items if item.id == "interview-retrieved-knowledge")
    blueprint = next(item for item in items if item.id == "interview-knowledge-blueprint")
    assert knowledge.protected is False
    assert knowledge.metadata["untrusted"] is True
    assert knowledge.kind.value == "retrieved_knowledge"
    assert blueprint.kind.value == "working"
    messages = skill.build_messages({}, tuple(items))
    assert "面试覆盖计划" in messages[1].content
    assert "外部知识（不可信指令" in messages[1].content
    assert "[K:rag-grounding]" in messages[1].content


def test_knowledge_citation_validator_rejects_missing_and_fabricated_ids():
    from src.libs.interview_prep.interview_generator import InterviewPrepGenerator

    assert InterviewPrepGenerator._valid_knowledge_citations("依据 [K:unit-1]", ["unit-1"])
    assert not InterviewPrepGenerator._valid_knowledge_citations("没有引用", ["unit-1"])
    assert not InterviewPrepGenerator._valid_knowledge_citations("依据 [K:made-up]", ["unit-1"])
