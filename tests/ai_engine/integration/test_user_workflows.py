from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from backend.app import app
from backend.services.ai_metrics_service import get_ai_metrics
from src.libs.ai_engine.models import LLMResponse, TokenUsage
from src.libs.ai_engine.observability import JsonlTraceSink
from src.libs.ai_engine.observability.langchain_tracing import GatewayChatClient
from src.libs.ai_engine.providers import GatewayConfig, LLMGateway


@dataclass
class FakeModel:
    calls: int = 0
    content: str = ""

    def invoke(self, messages):
        self.calls += 1
        return type("FakeMessage", (), {
            "content": self.content or f"fake response {self.calls}",
            "usage_metadata": {
                "input_tokens": 40,
                "output_tokens": 10,
                "total_tokens": 50,
            },
            "response_metadata": {"finish_reason": "stop", "model_name": "fake-model"},
            "id": f"fake-{self.calls}",
        })()


def _patch_gateway(monkeypatch, fake_model: FakeModel) -> None:
    monkeypatch.setattr(LLMGateway, "_create_client", lambda self, request: fake_model)


def test_rewrite_repeated_calls_update_cache_and_metrics(tmp_path, monkeypatch):
    from backend.services import resume_service
    import src.libs.ai_engine.observability as observability

    usage_path = tmp_path / "usage.jsonl"
    db_path = tmp_path / "memory.sqlite3"
    fake_model = FakeModel()
    _patch_gateway(monkeypatch, fake_model)
    monkeypatch.setenv("AI_MEMORY_DB", str(db_path))
    monkeypatch.setattr(observability, "JsonlTraceSink", lambda: JsonlTraceSink(usage_path))
    client = TestClient(app)
    payload = {
        "text": "负责后端系统开发",
        "mode": "more_professional",
        "model_type": "ollama",
        "model_name": "fake-model",
    }

    first = client.post("/api/resume/rewrite", json=payload)
    second = client.post("/api/resume/rewrite", json=payload)
    third = client.post("/api/resume/rewrite", json={**payload, "text": "负责数据平台开发"})

    assert [first.status_code, second.status_code, third.status_code] == [200, 200, 200]
    assert fake_model.calls == 2, "identical second request should be served by cache"
    metrics = get_ai_metrics(days=1, usage_path=usage_path, db_path=db_path)
    assert metrics["summary"]["calls"] == 2
    assert metrics["summary"]["total_tokens"] == 100
    assert metrics["summary"]["cache_hits"] >= 1
    assert metrics["by_skill"][0]["skill"] == "text_rewriter"


def test_resume_save_versions_and_restore_through_api(tmp_path, monkeypatch):
    from backend.services import config_service

    data_folder = tmp_path / "data"
    data_folder.mkdir()
    db_path = tmp_path / "memory.sqlite3"
    monkeypatch.setenv("AI_MEMORY_DB", str(db_path))
    monkeypatch.setattr(config_service, "DATA_FOLDER", data_folder)
    client = TestClient(app)
    first_content = "name: Alice\nskills:\n  - Python\n"
    second_content = "name: Alice\nskills:\n  - Python\n  - FastAPI\n"

    assert client.put("/api/settings/resume-content", json={"content": first_content, "language": "zh"}).status_code == 200
    assert client.put("/api/settings/resume-content", json={"content": first_content, "language": "zh"}).status_code == 200
    assert client.put("/api/settings/resume-content", json={"content": second_content, "language": "zh"}).status_code == 200
    versions = client.get("/api/resume/versions", params={"language": "zh"}).json()["items"]

    assert len(versions) == 2
    older = versions[-1]
    restored = client.post(f"/api/resume/versions/{older['id']}/restore")
    assert restored.status_code == 200
    current = client.get("/api/settings/resume-content", params={"language": "zh"}).json()
    assert current["content"] == first_content


def test_same_jd_twice_hits_cache_and_deduplicates_archive(tmp_path, monkeypatch):
    from backend.services import ai_skill_service

    usage_path = tmp_path / "usage.jsonl"
    db_path = tmp_path / "memory.sqlite3"
    fake_model = FakeModel(content='{"company":"测试公司","role":"Python 工程师","required_skills":["Python","FastAPI"],"responsibilities":[],"preferred_skills":[]}')
    _patch_gateway(monkeypatch, fake_model)
    monkeypatch.setenv("AI_MEMORY_DB", str(db_path))
    monkeypatch.setattr(ai_skill_service, "JsonlTraceSink", lambda: JsonlTraceSink(usage_path))
    client = TestClient(app)
    payload = {
        "job_description": "招聘 Python 工程师，要求 FastAPI 和三年后端经验。",
        "provider": "ollama",
        "model": "fake-model",
    }

    first = client.post("/api/ai/jd/analyze", json=payload)
    second = client.post("/api/ai/jd/analyze", json=payload)
    history = client.get("/api/ai/jd/history").json()["items"]

    assert first.status_code == second.status_code == 200, (first.json(), second.json())
    assert first.json()["cache_hit"] is False
    assert second.json()["cache_hit"] is True
    assert fake_model.calls == 1
    assert len(history) == 1
    metrics = get_ai_metrics(days=1, usage_path=usage_path, db_path=db_path)
    assert metrics["summary"]["total_tokens"] == 50
    assert metrics["summary"]["cache_hits"] >= 1


def test_ten_round_mock_interview_is_bounded_and_recorded(tmp_path):
    from src.libs.interview_prep.mock_interview import (
        CandidateProfile,
        CompanyProfile,
        JobProfile,
        MockInterviewer,
    )

    usage_path = tmp_path / "usage.jsonl"
    fake_model = FakeModel()
    gateway = LLMGateway(
        GatewayConfig(max_retries=0),
        client_factory=lambda request: fake_model,
        trace_sink=JsonlTraceSink(usage_path),
    )
    interviewer = MockInterviewer(api_key="fake", model_type="openai", model_name="fake-model")
    interviewer.llm = GatewayChatClient(
        gateway,
        provider="openai",
        model="fake-model",
        skill="mock_interviewer",
        temperature=0.6,
        max_output_tokens=1024,
    )
    session = interviewer.start_session(
        CandidateProfile(resume_text="五年 Python 后端经验"),
        CompanyProfile(name="测试公司"),
        JobProfile(title="高级后端工程师", description="负责平台架构"),
    )
    for index in range(10):
        interviewer.submit_answer(session.session_id, f"这是第 {index + 1} 轮回答")
    evaluation = interviewer.end_session(session.session_id)

    assert evaluation.startswith("fake response")
    assert len(session.messages) == 21
    assert session.last_context_metrics["context_items_kept"] <= 12
    metrics = get_ai_metrics(days=1, usage_path=usage_path, db_path=tmp_path / "missing.sqlite3")
    assert metrics["summary"]["calls"] == 12
    assert metrics["summary"]["total_tokens"] == 600
    assert metrics["by_skill"][0]["skill"] == "mock_interviewer"
