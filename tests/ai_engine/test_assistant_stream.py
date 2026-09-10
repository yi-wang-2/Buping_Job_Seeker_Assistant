from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.endpoints import assistant as assistant_endpoint
from backend.services.assistant_repository import AssistantRepository
from backend.services.assistant_service import AssistantService


def test_assistant_sse_streams_progress_before_validated_content(monkeypatch):
    class FakeService:
        def send_message(self, session_id, **kwargs):
            sink = kwargs["event_sink"]
            sink({"stage": "workspace_context", "detail": "已读取当前页面状态", "status": "completed"})
            sink({"stage": "skill", "detail": "正在执行整份简历评审", "status": "running"})
            sink({"stage": "harness", "detail": "评审依据校验完成", "status": "completed"})
            return {
                "user_message": {
                    "id": "u1", "session_id": session_id, "role": "user", "content": "分析简历",
                    "run_id": None, "status": "completed", "metadata": {}, "created_at": "now",
                },
                "assistant_message": {
                    "id": "a1", "session_id": session_id, "role": "assistant",
                    "content": "### 优点\n\n1. 结构清晰", "run_id": "r1", "status": "completed",
                    "metadata": {}, "created_at": "now",
                },
                "run": {"id": "r1", "status": "completed"},
                "proposal": None,
            }

    monkeypatch.setattr(assistant_endpoint, "service", lambda: FakeService())
    app = FastAPI()
    app.include_router(assistant_endpoint.router, prefix="/assistant")
    response = TestClient(app).post(
        "/assistant/sessions/s1/messages/stream",
        json={"message": "分析简历", "page": "resume"},
    )

    assert response.status_code == 200
    body = response.text
    assert body.index("event: progress") < body.index("event: result_start")
    assert body.index("event: result_start") < body.index("event: content_delta")
    assert body.index("event: content_delta") < body.index("event: result_end")
    assert body.count("event: content_delta") >= 2
    assert '"content":""' in body
    assert "结构清晰" in body


def test_assistant_attachment_upload_endpoint_extracts_text(tmp_path, monkeypatch):
    assistant_service = AssistantService(AssistantRepository(tmp_path / "upload.sqlite3"))
    monkeypatch.setattr(assistant_endpoint, "service", lambda: assistant_service)
    app = FastAPI()
    app.include_router(assistant_endpoint.router, prefix="/assistant")
    session = assistant_service.create_session("resume", "upload-test")["session"]

    response = TestClient(app).post(
        f"/assistant/sessions/{session['id']}/attachments",
        files={"file": ("岗位说明.txt", "负责 Agent Runtime 开发".encode("utf-8"), "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["filename"] == "岗位说明.txt"
    assert response.json()["character_count"] == len("负责 Agent Runtime 开发")
