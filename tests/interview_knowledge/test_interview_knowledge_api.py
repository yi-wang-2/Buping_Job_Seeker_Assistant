import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.endpoints import interview_knowledge
from backend.services.interview_knowledge_service import InterviewKnowledgeService


def test_preview_sync_search_debug_api(tmp_path, monkeypatch):
    source_root = tmp_path / "sources"
    source_root.mkdir()
    (source_root / "questions.json").write_text(json.dumps([{
        "question": "MCP 解决什么问题？", "answer": "标准化模型与工具的数据交换。",
        "thinking": "考察协议理解", "competencies": ["MCP"],
    }], ensure_ascii=False), encoding="utf-8")
    service = InterviewKnowledgeService(tmp_path / "knowledge.sqlite3", source_root)
    monkeypatch.setattr(interview_knowledge, "get_interview_knowledge_service", lambda: service)
    app = FastAPI()
    app.include_router(interview_knowledge.router, prefix="/api/interview-knowledge")
    client = TestClient(app)
    source = {
        "id": "mcp", "name": "MCP 题库", "source_type": "json",
        "location": "questions.json", "scope": "public", "license": "MIT",
    }

    preview = client.post("/api/interview-knowledge/preview", json=source)
    assert preview.status_code == 200
    assert preview.json()["unit_count"] == 1
    synced = client.post("/api/interview-knowledge/sync", json={"source": source})
    assert synced.status_code == 200
    assert synced.json()["vectors"]["indexed"] == 1
    searched = client.post("/api/interview-knowledge/search", json={"text": "MCP 工具协议"})
    assert searched.status_code == 200
    assert searched.json()["hits"][0]["unit"]["title"] == "MCP 解决什么问题？"
    assert client.get("/api/interview-knowledge/sources").json()["items"][0]["id"] == "mcp"


def test_api_rejects_unknown_fields_and_unlicensed_public_source(tmp_path, monkeypatch):
    source_root = tmp_path / "sources"
    source_root.mkdir()
    (source_root / "empty.json").write_text("[]", encoding="utf-8")
    service = InterviewKnowledgeService(tmp_path / "knowledge.sqlite3", source_root)
    monkeypatch.setattr(interview_knowledge, "get_interview_knowledge_service", lambda: service)
    app = FastAPI()
    app.include_router(interview_knowledge.router, prefix="/api/interview-knowledge")
    client = TestClient(app)

    invalid = client.post("/api/interview-knowledge/preview", json={
        "id": "x", "name": "x", "source_type": "json", "location": "empty.json",
        "unknown": "not allowed",
    })
    assert invalid.status_code == 422
    unlicensed = client.post("/api/interview-knowledge/preview", json={
        "id": "x", "name": "x", "source_type": "json", "location": "empty.json",
    })
    assert unlicensed.status_code == 400
    assert "license" in unlicensed.json()["detail"]


def test_user_can_upload_select_disable_and_delete_private_markdown(tmp_path, monkeypatch):
    service = InterviewKnowledgeService(tmp_path / "knowledge.sqlite3", tmp_path / "sources")
    monkeypatch.setattr(interview_knowledge, "get_interview_knowledge_service", lambda: service)
    app = FastAPI()
    app.include_router(interview_knowledge.router, prefix="/api/interview-knowledge")
    client = TestClient(app)

    uploaded = client.post(
        "/api/interview-knowledge/upload",
        data={"user_id": "alice", "domain_pack": "java"},
        files={"file": ("notes.md", "# JVM\n垃圾回收需要分析可达性。".encode("utf-8"), "text/markdown")},
    )
    assert uploaded.status_code == 200
    source_id = uploaded.json()["source"]["id"]
    assert uploaded.json()["preview"]["unit_count"] == 1
    assert client.get("/api/interview-knowledge/sources", params={"user_id": "alice"}).json()["items"][0]["stats"]["units"] == 1

    disabled = client.patch(
        f"/api/interview-knowledge/sources/{source_id}/status",
        json={"enabled": False, "user_id": "alice"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["sync_status"] == "disabled"
    assert client.delete(
        f"/api/interview-knowledge/sources/{source_id}", params={"user_id": "bob"},
    ).status_code == 403
    assert client.delete(
        f"/api/interview-knowledge/sources/{source_id}", params={"user_id": "alice"},
    ).json() == {"deleted": True}


def test_rejected_private_upload_does_not_leave_source_file(tmp_path, monkeypatch):
    source_root = tmp_path / "sources"
    service = InterviewKnowledgeService(tmp_path / "knowledge.sqlite3", source_root)
    monkeypatch.setattr(interview_knowledge, "get_interview_knowledge_service", lambda: service)
    app = FastAPI()
    app.include_router(interview_knowledge.router, prefix="/api/interview-knowledge")
    client = TestClient(app)

    rejected = client.post(
        "/api/interview-knowledge/upload",
        data={"user_id": "alice"},
        files={
            "file": (
                "secret.md",
                b"# private\napi_key=abcdefghijklmnop",
                "text/markdown",
            )
        },
    )

    assert rejected.status_code == 400
    assert list(source_root.rglob("secret.md")) == []
    assert list(source_root.rglob("user-*-secret.md")) == []


def test_public_catalog_can_be_installed_rebuilt_and_removed_through_api(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps({
        "schema_version": "1", "sources": [{
            "id": "agent-pack", "name": "Agent Pack", "description": "Agent 面试资料",
            "repository_url": "https://example.com/agent.git", "revision": "b" * 40,
            "source_type": "git", "domain_pack": "ai_agent", "license": "MIT",
            "license_notice": "测试许可说明", "license_evidence_path": "README.md",
            "license_evidence_text": "MIT License", "required_paths": ["README.md", "data.json"],
        }],
    }, ensure_ascii=False), encoding="utf-8")
    service = InterviewKnowledgeService(
        tmp_path / "knowledge.sqlite3", tmp_path / "sources", catalog_path,
    )

    def fake_checkout(spec, destination):
        (destination / "README.md").write_text("MIT License", encoding="utf-8")
        (destination / "data.json").write_text(json.dumps([{
            "question": "什么是 Agent Loop？", "answer": "规划、执行、观察和迭代。",
        }], ensure_ascii=False), encoding="utf-8")
        service._validate_catalog_checkout(spec, destination)

    monkeypatch.setattr(service, "_checkout_catalog_source", fake_checkout)
    monkeypatch.setattr(interview_knowledge, "get_interview_knowledge_service", lambda: service)
    app = FastAPI()
    app.include_router(interview_knowledge.router, prefix="/api/interview-knowledge")
    client = TestClient(app)

    available = client.get("/api/interview-knowledge/catalog")
    assert available.status_code == 200
    assert available.json()["items"][0]["installed"] is False
    assert client.post(
        "/api/interview-knowledge/catalog/agent-pack/install",
        json={"accept_license": False},
    ).status_code == 400

    installed = client.post(
        "/api/interview-knowledge/catalog/agent-pack/install",
        json={"accept_license": True},
    )
    assert installed.status_code == 200
    assert installed.json()["catalog"]["installed"] is True
    assert client.post(
        "/api/interview-knowledge/catalog/agent-pack/rebuild", json={},
    ).status_code == 200
    assert client.delete("/api/interview-knowledge/catalog/agent-pack").json() == {"deleted": True}
