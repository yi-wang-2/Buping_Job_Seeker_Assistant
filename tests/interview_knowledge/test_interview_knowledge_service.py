import json

import pytest

from backend.services.interview_knowledge_service import InterviewKnowledgeService


def _payload(location="questions.json", license_name="MIT"):
    return {
        "id": "questions", "name": "面试题", "source_type": "json",
        "location": location, "scope": "public", "license": license_name,
        "domain_pack": "interview",
    }


def _write_catalog(path, *, revision="a" * 40):
    path.write_text(json.dumps({
        "schema_version": "1",
        "sources": [{
            "id": "public-agent", "name": "Agent 公共库",
            "description": "用于测试的公共知识库",
            "repository_url": "https://example.com/agent.git",
            "revision": revision, "source_type": "git", "domain_pack": "ai_agent",
            "license": "MIT", "license_notice": "测试许可说明",
            "license_evidence_path": "README.md", "license_evidence_text": "MIT License",
            "required_paths": ["README.md", "data.json"],
            "accept_import_warnings": False,
        }],
    }, ensure_ascii=False), encoding="utf-8")


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


def test_catalog_install_rebuild_and_uninstall_generate_local_index(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    _write_catalog(catalog_path)
    source_root = tmp_path / "sources"
    service = InterviewKnowledgeService(
        tmp_path / "knowledge.sqlite3", source_root, catalog_path,
    )

    def fake_checkout(spec, destination):
        (destination / "README.md").write_text("# MIT License", encoding="utf-8")
        (destination / "data.json").write_text(json.dumps([{
            "question": "Agent 如何规划？", "answer": "先拆解目标，再执行和校验。",
            "thinking": "考察 Agent Loop",
        }], ensure_ascii=False), encoding="utf-8")
        service._validate_catalog_checkout(spec, destination)

    monkeypatch.setattr(service, "_checkout_catalog_source", fake_checkout)

    with pytest.raises(ValueError, match="license acceptance"):
        service.install_catalog_source("public-agent", accept_license=False)
    installed = service.install_catalog_source("public-agent", accept_license=True)
    assert installed["sync"]["created"] == 1
    assert installed["catalog"]["installed"] is True
    assert installed["catalog"]["managed_copy"] is True
    assert installed["catalog"]["installed_revision"] == "a" * 40
    assert installed["catalog"]["stats"]["units"] == 1
    assert service.search({"text": "Agent 规划", "top_k": 3})["hits"]

    rebuilt = service.rebuild_catalog_source("public-agent")
    assert rebuilt["sync"]["unchanged"] == 1
    assert service.uninstall_catalog_source("public-agent") is True
    assert service.repository.get_source("public-agent") is None
    assert not (source_root / "public" / "public-agent").exists()
    assert service.uninstall_catalog_source("public-agent") is False


def test_catalog_recognizes_and_can_remove_legacy_local_checkout(tmp_path):
    catalog_path = tmp_path / "catalog.json"
    _write_catalog(catalog_path)
    source_root = tmp_path / "sources"
    legacy = source_root / "public-agent"
    legacy.mkdir(parents=True)
    (legacy / "README.md").write_text("MIT License\n\nAgent notes", encoding="utf-8")
    (legacy / "data.json").write_text("[]", encoding="utf-8")
    service = InterviewKnowledgeService(
        tmp_path / "knowledge.sqlite3", source_root, catalog_path,
    )
    service.sync({
        "id": "public-agent", "name": "Agent 公共库", "source_type": "git",
        "location": "public-agent", "scope": "public", "license": "MIT",
        "domain_pack": "ai_agent",
    })

    item = service.list_catalog()[0]

    assert item["installed"] is True
    assert item["managed_copy"] is False
    assert item["update_available"] is True
    assert service.uninstall_catalog_source("public-agent") is True
    assert not legacy.exists()
