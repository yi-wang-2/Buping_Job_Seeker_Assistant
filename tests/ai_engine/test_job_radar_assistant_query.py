from types import SimpleNamespace

from backend.services.assistant_repository import AssistantRepository
from backend.services.assistant_service import AssistantService
from src.libs.ai_engine.models import TokenUsage
from src.libs.ai_engine.skills import SkillResult


def test_database_question_uses_authoritative_query_result(tmp_path, monkeypatch):
    calls = []

    class FakeRuntime:
        def execute(self, skill_name, inputs, **kwargs):
            calls.append((skill_name, inputs))
            if skill_name == "assistant_supervisor":
                assert "job_radar_query" in inputs["available_skills"]
                return SkillResult(
                    content="route",
                    structured_output={
                        "kind": "skill_call",
                        "intent": "count_companies",
                        "target_refs": [],
                        "name": "job_radar_query",
                        "arguments": {"operation": "distinct_count", "metric": "companies"},
                        "response": "",
                        "follow_up": "",
                        "reason_code": "database_fact_requires_query",
                    },
                    usage=TokenUsage(8, 4, 12),
                )
            assert skill_name == "direct_chat"
            result = inputs["workspace_context"]["job_radar_query_result"]
            assert result["scope"] == "database"
            assert result["value"] == 87
            assert inputs["workspace_context"]["query_result_is_authoritative"] is True
            return SkillResult(content="库中共有 87 家公司。", usage=TokenUsage(7, 3, 10))

    monkeypatch.setattr(
        "backend.services.assistant_service.build_ai_runtime",
        lambda *args, **kwargs: SimpleNamespace(runtime=FakeRuntime()),
    )
    monkeypatch.setattr(
        "backend.services.assistant_service.execute_job_radar_query",
        lambda arguments: {
            "schema_version": "1", "operation": "distinct_count", "scope": "database",
            "metric": "companies", "filters_applied": {"status": "active"}, "value": 87,
            "rows": [], "returned_count": 0, "total_count": 87, "truncated": False,
            "as_of": "2026-09-10T10:00:00+08:00", "source": "job_radar.sqlite3",
        },
    )

    service = AssistantService(AssistantRepository(tmp_path / "assistant.sqlite3"))
    session = service.create_session("job-radar", "general")["session"]
    result = service.send_message(
        session["id"], message="库中有几家公司？", page="job-radar",
        workspace_snapshot={
            "language": "zh",
            "job_results": [{"company": f"样本公司{i}"} for i in range(20)],
        },
        api_key="test-key", provider="openai", model="test-model",
    )

    assert "87 家公司" in result["assistant_message"]["content"]
    assert [name for name, _ in calls] == ["assistant_supervisor", "direct_chat"]
    with service.repository.memory.connection() as db:
        step = db.execute(
            "SELECT skill_name, observation_json FROM assistant_steps WHERE run_id=?",
            (result["run"]["id"],),
        ).fetchone()
    assert step["skill_name"] == "job_radar_query"
    assert '"total_count":87' in step["observation_json"]
