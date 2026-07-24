from types import SimpleNamespace

from backend.services.ai_metrics_service import get_ai_metrics
from src.libs.ai_engine.observability.langchain_tracing import TracedChatClient
from src.libs.ai_engine.observability.tracing import JsonlTraceSink


class FakeChatClient:
    def invoke(self, _messages):
        return SimpleNamespace(
            content="generated report",
            usage_metadata={"input_tokens": 120, "output_tokens": 80, "total_tokens": 200},
            response_metadata={"model_name": "test-model", "finish_reason": "stop"},
            id="test-response",
        )


def test_interview_call_is_included_in_ai_metrics(tmp_path):
    usage_path = tmp_path / "ai_usage.jsonl"
    client = TracedChatClient(
        FakeChatClient(),
        provider="openai",
        model="test-model",
        skill="interview_coach",
        temperature=0.4,
        max_output_tokens=4096,
        trace_sink=JsonlTraceSink(usage_path),
    )

    response = client.invoke([{"role": "user", "content": "private prompt"}])
    metrics = get_ai_metrics(days=1, usage_path=usage_path, db_path=tmp_path / "missing.sqlite3")

    assert response.content == "generated report"
    assert metrics["summary"]["calls"] == 1
    assert metrics["summary"]["total_tokens"] == 200
    assert metrics["by_skill"][0]["skill"] == "interview_coach"
    assert "private prompt" not in usage_path.read_text(encoding="utf-8")
