from __future__ import annotations

import sqlite3

import pytest
from pydantic import ValidationError

from backend.services import job_radar_query_service
from src.libs.ai_engine.assistant import AssistantGraphFacade, SupervisorTurn


def _unused_supervisor(_observations, _request):
    raise AssertionError("deterministic job report must not call the supervisor")


def test_strict_route_rejects_missing_capability_name():
    with pytest.raises(ValidationError):
        SupervisorTurn(
            kind="skill_call", intent="query", name=None,
            reason_code="invalid",
        )


def test_job_report_interrupt_resumes_original_task_from_sqlite_checkpoint(tmp_path):
    checkpoint = tmp_path / "assistant-graph.sqlite3"
    executed = []

    def execute(turn, request):
        executed.append((turn, request))
        return {"content": "完整报告", "usage": {"total_tokens": 7}}

    first = AssistantGraphFacade(
        checkpoint, supervisor=_unused_supervisor, executor=execute,
    ).invoke(
        session_id="session-1", page="job-radar",
        request={"message": "今日就业形势如何", "page": "job-radar"},
    )
    assert first.interrupted is True
    assert first.turn and first.turn.kind == "clarification"
    assert executed == []

    resumed = AssistantGraphFacade(
        checkpoint, supervisor=_unused_supervisor, executor=execute,
    ).invoke(
        session_id="session-1", page="job-radar",
        request={"message": "所有维度", "page": "job-radar"},
    )
    assert resumed.resumed is True
    assert resumed.interrupted is False
    assert resumed.result == {"content": "完整报告", "usage": {"total_tokens": 7}}
    turn, request = executed[0]
    assert turn.name == "job_market_report"
    assert turn.arguments["dimensions"] == [
        "location", "industry", "company_type", "recruitment_type", "scene", "match_level", "company",
    ]
    assert "今日就业形势如何" in request["message"]
    assert "所有维度" in request["message"]

    def supervisor(_observations, request):
        assert request["message"] == "帮我看看当前岗位"
        return SupervisorTurn(
            kind="skill_call", intent="query", name="direct_chat",
            arguments={}, reason_code="new_turn",
        )

    new_turn = AssistantGraphFacade(
        checkpoint, supervisor=supervisor,
        executor=lambda turn, request: {"content": f"{turn.name}:{request['message']}"},
    ).invoke(
        session_id="session-1", page="job-radar",
        request={"message": "帮我看看当前岗位", "page": "job-radar"},
    )
    assert new_turn.interrupted is False
    assert new_turn.turn and new_turn.turn.name == "direct_chat"
    assert new_turn.result == {"content": "direct_chat:帮我看看当前岗位"}


def test_market_report_reads_domain_rows_once_for_all_dimensions(tmp_path, monkeypatch):
    calls = 0

    def rows(_path):
        nonlocal calls
        calls += 1
        return [
            {"company": "甲", "location": "南京", "industry": "AI", "company_type": "民企",
             "recruitment_type": "校招", "scene": "general", "match_level": "高匹配", "source": "a"},
            {"company": "乙", "location": "上海", "industry": "AI", "company_type": "国企/央企",
             "recruitment_type": "社招", "scene": "general", "match_level": "中匹配", "source": "b"},
        ]

    monkeypatch.setattr(job_radar_query_service, "_domain_rows", rows)
    result = job_radar_query_service.execute_job_market_report(
        ["location", "industry", "company_type"], tmp_path / "jobs.sqlite3",
    )
    assert calls == 1
    assert result["job_count"] == 2
    assert result["company_count"] == 2
    assert result["scope_label"] == "当前本地岗位库"
    assert result["distributions"]["industry"] == [{"key": "AI", "count": 2}]


def test_checkpoint_serializer_rejects_non_json_payloads(tmp_path):
    checkpoint = tmp_path / "assistant-graph.sqlite3"
    facade = AssistantGraphFacade(checkpoint, supervisor=_unused_supervisor, executor=lambda *_: {})
    first = facade.invoke(
        session_id="safe", page="job-radar",
        request={"message": "今日就业形势如何", "page": "job-radar"},
    )
    assert first.interrupted
    with sqlite3.connect(checkpoint) as db:
        types = {row[0] for row in db.execute(
            "SELECT type FROM checkpoints UNION SELECT type FROM writes"
        )}
    assert types == {"json"}


def test_proposal_waits_for_explicit_approval_and_then_finishes(tmp_path):
    checkpoint = tmp_path / "assistant-graph.sqlite3"

    def supervisor(_observations, _request):
        return SupervisorTurn(
            kind="action_proposal", intent="favorite", name="favorite_job",
            arguments={"job_id": "job-1"}, reason_code="requested",
        )

    def execute(_turn, _request):
        return {
            "proposal": {"id": "proposal-1", "proposal_type": "job_radar_action", "risk": "low"},
            "usage": {},
        }

    facade = AssistantGraphFacade(checkpoint, supervisor=supervisor, executor=execute)
    pending = facade.invoke(
        session_id="proposal-session", page="job-radar",
        request={"message": "收藏这个岗位", "page": "job-radar"},
    )
    assert pending.interrupted is True
    assert pending.result and pending.result["proposal"]["id"] == "proposal-1"
    resumed = facade.resume_approval(session_id="proposal-session", approved=True)
    assert resumed and resumed["terminal_reason"] == "proposal_applied"
