import json

import pytest

from backend.services.interview_knowledge_service import InterviewKnowledgeService


def _payload(location="questions.json", license_name="MIT"):
    return {
        "id": "questions", "name": "面试题", "source_type": "json",
        "location": location, "scope": "public", "license": license_name,
        "domain_pack": "interview",
    }


def test_preview_sync_search_and_incremental_update(tmp_path):
    source_root = tmp_path / "sources"
    source_root.mkdir()
    source = source_root / "questions.json"
    source.write_text(json.dumps([{
        "question": "RAG 如何减少幻觉？", "answer": "检索依据并提供引用。",
        "thinking": "考察 grounding", "competencies": ["RAG"],
    }], ensure_ascii=False), encoding="utf-8")
    service = InterviewKnowledgeService(tmp_path / "knowledge.sqlite3", source_root)

    preview = service.preview(_payload())
    assert preview["unit_count"] == 1
    assert preview["sample_units"][0]["metadata"]["interviewer_intent"] == "考察 grounding"
    first = service.sync(_payload())
    assert first["created"] == 1
    assert first["vectors"]["indexed"] == 1
    result = service.search({"text": "RAG 引用", "top_k": 3})
    assert result["hits"][0]["unit"]["title"] == "RAG 如何减少幻觉？"

    source.write_text(json.dumps([{
        "question": "RAG 如何减少幻觉？", "answer": "检索、重排并逐条验证引用。",
        "thinking": "考察 grounding", "competencies": ["RAG"],
    }], ensure_ascii=False), encoding="utf-8")
    second = service.sync(_payload())
    assert second["updated"] == 1
    assert second["vectors"]["indexed"] == 1


def test_service_rejects_path_escape_and_unlicensed_public_source(tmp_path):
    source_root = tmp_path / "sources"
    source_root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("[]", encoding="utf-8")
    inside = source_root / "inside.json"
    inside.write_text("[]", encoding="utf-8")
    service = InterviewKnowledgeService(tmp_path / "knowledge.sqlite3", source_root)

    with pytest.raises(ValueError, match="inside"):
        service.preview(_payload("../outside.json"))
    with pytest.raises(ValueError, match="license"):
        service.preview(_payload("inside.json", ""))
