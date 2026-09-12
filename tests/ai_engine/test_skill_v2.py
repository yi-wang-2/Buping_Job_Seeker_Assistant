from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

from src.libs.ai_engine.memory import MemoryItem, MemoryManager, SQLiteMemoryRepository
from src.libs.ai_engine.models import LLMResponse
from src.libs.ai_engine.optimization import PromptCache
from src.libs.ai_engine.providers import GatewayConfig, LLMGateway
from src.libs.ai_engine.runtime import AIRuntime
from src.libs.ai_engine.skills import SkillResult
from src.libs.ai_engine.skills.builtin import CareerAdvisorSkill, JobStatusClassifierSkill, TextRewriterSkill
from src.libs.ai_engine.skills.factory import create_builtin_registry


@dataclass
class FakeResponse:
    content: str
    response_metadata: dict | None = None
    usage_metadata: dict | None = None

    def __post_init__(self) -> None:
        self.response_metadata = {"finish_reason": "stop", "model_name": "fake"}
        self.usage_metadata = {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}


class FakeClient:
    def __init__(self, content: str = "改写结果") -> None:
        self.content = content
        self.calls = 0
        self.messages = []

    def invoke(self, messages):
        self.calls += 1
        self.messages.append(messages)
        return FakeResponse(self.content)


def test_builtin_registry_is_discoverable_and_every_skill_has_an_input_schema():
    registry = create_builtin_registry()
    descriptions = registry.describe()
    names = {item["name"] for item in descriptions}

    assert {
        "resume_writer", "mock_interviewer", "interview_coach", "text_rewriter",
        "resume_reviewer", "jd_analyzer", "skill_matcher", "career_advisor", "job_status_classifier",
        "job_recommender",
        "direct_chat",
    } == names
    assert all(skill.metadata.input_schema is not None for skill in registry.list())

    registry.disable("career_advisor")
    with pytest.raises(ValueError, match="disabled"):
        registry.get("career_advisor")
    registry.enable("career_advisor")
    assert registry.get("career_advisor").metadata.name == "career_advisor"


def test_cache_hit_reports_zero_actual_usage_and_records_runs(tmp_path):
    repo = SQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    cache = PromptCache(repo.path)
    client = FakeClient()
    gateway = LLMGateway(GatewayConfig(), client_factory=lambda _: client)
    registry = create_builtin_registry()
    runtime = AIRuntime(gateway, registry, cache, repository=repo, memory_manager=MemoryManager(repo))
    inputs = {"text": "测试", "mode": "fix_grammar", "target_language": "zh"}

    first = runtime.execute("text_rewriter", inputs, provider="fake", model="fake")
    second = runtime.execute("text_rewriter", inputs, provider="fake", model="fake")

    assert first.usage.total_tokens == 7
    assert second.cache_hit is True
    assert second.usage.total_tokens == 0
    assert second.cached_usage.total_tokens == 7
    assert first.trace_id and second.trace_id and first.trace_id != second.trace_id
    assert first.run_id and second.run_id
    with sqlite3.connect(repo.path) as db:
        rows = db.execute("SELECT usage_json, cache_hit FROM skill_runs ORDER BY started_at").fetchall()
    assert len(rows) == 2
    assert rows[-1][1] == 1
    assert json.loads(rows[-1][0])["total_tokens"] == 0


def test_declared_memory_is_loaded_into_skill_context(tmp_path):
    repo = SQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    repo.upsert_memory(MemoryItem("job_preferences", "target_role", "AI Agent 开发"))
    client = FakeClient(
        '{"summary":"建议内容","priorities":[],"action_plan":[],"assumptions":[]}'
    )
    gateway = LLMGateway(GatewayConfig(), client_factory=lambda _: client)
    registry = create_builtin_registry()
    runtime = AIRuntime(gateway, registry, memory_manager=MemoryManager(repo), repository=repo)

    result = runtime.execute(
        "career_advisor", {"resume": "Python 开发经历", "goals": "进入 AI Agent 团队"},
        provider="fake", model="fake",
    )

    assert result.memories_used
    assert "AI Agent 开发" in client.messages[0][1]["content"]
    saved = repo.list_memories("local", "career_goals")
    assert saved[0].value == "进入 AI Agent 团队"


def test_unavailable_tool_is_rejected_before_model_invocation():
    client = FakeClient()
    gateway = LLMGateway(GatewayConfig(), client_factory=lambda _: client)
    skill = TextRewriterSkill()
    skill.metadata = replace(skill.metadata, tools=("load_resume",))
    registry = create_builtin_registry()
    registry.register(skill, replace=True)

    with pytest.raises(PermissionError, match="load_resume"):
        AIRuntime(gateway, registry).execute(
            "text_rewriter",
            {"text": "测试", "mode": "fix_grammar", "target_language": "zh"},
            provider="fake", model="fake",
        )
    assert client.calls == 0


def test_job_status_classifier_requires_verbatim_evidence():
    valid = FakeClient(
        '{"matched_application":true,"normalized_status":"一面",'
        '"raw_status":"技术面试","confidence":0.96,"reason":"页面明确显示"}'
    )
    gateway = LLMGateway(GatewayConfig(), client_factory=lambda _: valid)
    registry = create_builtin_registry()
    result = AIRuntime(gateway, registry).execute(
        JobStatusClassifierSkill.metadata.name,
        {"page_context": "当前状态：技术面试", "company": "测试公司", "role": "AI Agent"},
        provider="fake", model="fake",
    )
    assert result.structured_output["normalized_status"] == "一面"

    hallucinated = FakeClient(
        '{"matched_application":true,"normalized_status":"Offer",'
        '"raw_status":"录用通知","confidence":0.99,"reason":"推测"}'
    )
    bad_runtime = AIRuntime(
        LLMGateway(GatewayConfig(), client_factory=lambda _: hallucinated), registry,
    )
    with pytest.raises(ValueError, match="原文") as captured:
        bad_runtime.execute(
            JobStatusClassifierSkill.metadata.name,
            {"page_context": "当前状态：技术面试", "company": "测试公司", "role": "AI Agent"},
            provider="fake", model="fake",
        )
    assert captured.value.skill_usage.total_tokens == 7


def test_job_status_classifier_repairs_missing_json_comma_without_changing_values():
    raw = (
        '{"matched_application":true,"normalized_status":"简历筛选",'
        '"raw_status":"筛选中","confidence":0.8,'
        '"application_match_confidence":0.8,"status_confidence":0.9,'
        '"reason":"三个岗位"\n"applications":[]}'
    )
    result = JobStatusClassifierSkill().parse_output(LLMResponse(raw, "fake", "fake"))
    assert result.structured_output["reason"] == "三个岗位"
    assert result.structured_output["applications"] == []
    assert result.warnings == ("json_syntax_repaired",)


def test_mock_interview_legacy_adapter_executes_registered_skill(monkeypatch):
    from backend.services import ai_runtime_service
    from src.libs.interview_prep.mock_interview import _create_chat_model

    class FakeRuntime:
        def __init__(self) -> None:
            self.calls = []

        def execute(self, skill_name, inputs, **kwargs):
            self.calls.append((skill_name, inputs, kwargs))
            return SkillResult(content="下一题", trace_id="trace-1")

    runtime = FakeRuntime()
    monkeypatch.setattr(
        ai_runtime_service,
        "build_ai_runtime",
        lambda *args, **kwargs: SimpleNamespace(runtime=runtime),
    )
    client = _create_chat_model("fake", "openai", "", "fake-model")
    response = client.invoke([{"role": "user", "content": "完整的面试上下文"}])

    assert response.content == "下一题"
    assert runtime.calls[0][0] == "mock_interviewer"
    assert runtime.calls[0][1]["prepared_prompt"] == "完整的面试上下文"
