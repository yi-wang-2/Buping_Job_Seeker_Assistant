from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.endpoints import settings as settings_endpoint
from backend.services import llm_connection_service
from src.libs.ai_engine.models import LLMResponse


def test_connection_error_has_actionable_diagnosis():
    code, message = llm_connection_service.diagnose_llm_error(
        RuntimeError("minimax-anth invocation failed: Connection error")
    )

    assert code == "connection_failed"
    assert "API 地址" in message
    assert "后端进程" in message


def test_connection_check_uses_entered_configuration(monkeypatch):
    captured = {}

    class FakeGateway:
        def __init__(self, config):
            captured["config"] = config

        def invoke(self, request):
            captured["request"] = request
            return LLMResponse(content="OK", model=request.model, provider=request.provider, latency_ms=37)

    monkeypatch.setattr(llm_connection_service, "LLMGateway", FakeGateway)

    result = llm_connection_service.test_llm_connection(
        api_key="secret", provider="minimax-anth", model="MiniMax-M3",
        base_url="https://api.minimaxi.com/anthropic/",
    )

    assert result["success"] is True
    assert result["latency_ms"] == 37
    assert result["base_url"] == "https://api.minimaxi.com/anthropic"
    assert captured["request"].provider == "minimax-anth"
    assert captured["request"].model == "MiniMax-M3"
    assert captured["config"].api_key == "secret"


def test_connection_endpoint_returns_structured_failure(monkeypatch):
    def fail(**_):
        raise RuntimeError("Connection error")

    monkeypatch.setattr(llm_connection_service, "test_llm_connection", fail)
    app = FastAPI()
    app.include_router(settings_endpoint.router, prefix="/settings")

    response = TestClient(app).post("/settings/llm/test", json={
        "llm_api_key": "secret",
        "llm_model_type": "minimax-anth",
        "llm_model": "MiniMax-M3",
        "llm_base_url": "https://api.minimaxi.com/anthropic",
    })

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "connection_failed"
    assert "ProviderInvocationError" not in response.text
