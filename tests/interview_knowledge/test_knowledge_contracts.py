from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.libs.ai_engine.knowledge import KnowledgeQuery, KnowledgeSource, KnowledgeUnit
from src.libs.ai_engine.knowledge.evaluation import evaluate_no_rag_cases


def test_private_sources_and_session_queries_require_scope_identity():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        KnowledgeSource(
            id="private", name="私有知识", source_type="upload", location="resume.pdf",
            scope="user", created_at=now,
        )
    with pytest.raises(ValidationError):
        KnowledgeQuery(text="追问项目难点", scopes=["public", "session"])


def test_question_card_preserves_question_answer_and_intent_binding():
    unit = KnowledgeUnit(
        id="q1", source_id="source1", unit_type="question_card", title="HashMap 扩容",
        content="解释 HashMap 扩容过程。", domain="interview", topic="Java",
        source_path="data.json#q1", content_hash="abc", metadata={
            "question": "HashMap 如何扩容？",
            "reference_answer": "容量翻倍并重新分配桶。",
            "competencies": ["Java 集合"],
            "interviewer_intent": "考察集合实现和边界条件。",
        },
    )
    assert unit.metadata["reference_answer"].startswith("容量翻倍")
    with pytest.raises(ValidationError):
        KnowledgeUnit(
            id="bad", source_id="source1", unit_type="question_card", title="残缺题目",
            content="只有问题", domain="interview", source_path="x", content_hash="x",
            metadata={"question": "问题"},
        )


def test_user_evidence_requires_explicit_confirmation():
    with pytest.raises(ValidationError):
        KnowledgeUnit(
            id="u1", source_id="user", unit_type="user_evidence", title="项目经历",
            content="候选人的项目", domain="interview", source_path="resume",
            content_hash="hash", metadata={"confirmed": False},
        )


def test_no_rag_baseline_reports_coverage_repeat_tokens_and_latency():
    result = evaluate_no_rag_cases([{
        "id": "case-1", "expected_topics": ["Java", "数据库"],
        "covered_topics": ["java"], "questions": ["什么是索引？", "什么是索引？"],
        "input_tokens": 100, "output_tokens": 50, "latency_ms": 1200,
    }])
    assert result["topic_coverage"] == 0.5
    assert result["repeat_rate"] == 0.5
    assert result["average_tokens"] == 150
    assert result["average_latency_ms"] == 1200


def test_k0_golden_queries_and_interview_scripts_have_stable_ids_and_coverage():
    root = Path(__file__).resolve().parents[1] / "fixtures" / "interview_knowledge"
    queries = json.loads((root / "golden_queries.json").read_text(encoding="utf-8"))["cases"]
    scripts = json.loads((root / "interview_scripts.json").read_text(encoding="utf-8"))["scripts"]

    assert len(queries) >= 8
    assert len({case["id"] for case in queries}) == len(queries)
    assert all(case["query"] and case["expected_terms"] and case["expected_competencies"] for case in queries)
    assert {script["target_role"] for script in scripts} == {"后端工程师", "AI Agent 工程师"}
    assert all("closing" in script["stages"] and len(script["required_behaviors"]) >= 5 for script in scripts)
