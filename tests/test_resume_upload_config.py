from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.endpoints import settings as settings_endpoint
from backend.services import config_service
from src.libs.resume_and_cover_builder.document_parser import _empty_resume


def test_resume_upload_uses_multipart_model_configuration(monkeypatch):
    captured = {}

    monkeypatch.setattr(config_service, "load_secrets", lambda: {
        "llm_api_key": "stale-key",
        "llm_model_type": "anthropic",
        "llm_model": "stale-model",
    })

    def fake_parse(filename, content, **kwargs):
        captured.update(kwargs)
        return _empty_resume()

    monkeypatch.setattr(settings_endpoint, "parse_document", fake_parse)
    app = FastAPI()
    app.include_router(settings_endpoint.router, prefix="/settings")

    response = TestClient(app).post(
        "/settings/upload-resume",
        files={"file": ("resume.txt", b"complete resume text", "text/plain")},
        data={
            "target_lang": "zh",
            "api_key": "current-key",
            "model_type": "minimax-anth",
            "model_name": "MiniMax-M3",
            "base_url": "https://api.minimaxi.com/anthropic",
            "llm_protocol": "anthropic",
        },
    )

    assert response.status_code == 200
    assert captured["api_key"] == "current-key"
    assert captured["model_type"] == "minimax-anth"
    assert captured["model_name"] == "MiniMax-M3"
    assert captured["base_url"] == "https://api.minimaxi.com/anthropic"
    assert captured["target_lang"] == "zh"


def test_resume_upload_returns_safe_authentication_message(monkeypatch):
    def fail(*_, **__):
        raise RuntimeError("anthropic invocation failed: Error code: 401 invalid api key")

    monkeypatch.setattr(settings_endpoint, "parse_document", fail)
    app = FastAPI()
    app.include_router(settings_endpoint.router, prefix="/settings")

    response = TestClient(app).post(
        "/settings/upload-resume",
        files={"file": ("resume.txt", b"resume", "text/plain")},
        data={"api_key": "invalid", "model_type": "minimax-anth", "model_name": "MiniMax-M3"},
    )

    assert response.status_code == 401
    assert "检查 API 密钥" in response.json()["detail"]
    assert "invalid api key" not in response.json()["detail"]
