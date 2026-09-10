"""Opt-in real-model smoke tests for the controlled Assistant Runtime.

Run explicitly with:
    RUN_LIVE_LLM_TESTS=1 pytest tests/ai_engine/live/test_assistant_real_model.py -s

The suite keeps model usage bounded and covers routing plus end-to-end resume
rewrite/review flows. Run it only through the explicit environment flag.
"""

from __future__ import annotations

import os
from dataclasses import replace

import pytest

from backend.services.ai_runtime_service import build_ai_runtime
from backend.services.ai_skill_service import _resolve_config
from backend.services.assistant_repository import AssistantRepository
from backend.services.assistant_service import AssistantService
from src.libs.ai_engine.assistant import AssistantSupervisorSkill, SupervisorTurn
from src.libs.ai_engine.context import TokenBudget


pytestmark = pytest.mark.live_llm


def _live_config() -> dict[str, str]:
    if os.getenv("RUN_LIVE_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_LLM_TESTS=1 to allow real model calls")
    config = _resolve_config("", "", "", "")
    if not config["api_key"] and config["provider"].lower() != "ollama":
        pytest.skip("No LLM API key configured")
    return config


def _bounded_supervisor() -> AssistantSupervisorSkill:
    skill = AssistantSupervisorSkill()
    skill.metadata = replace(
        skill.metadata,
        token_budget=TokenBudget(
            model_context_limit=12000,
            reserved_output=2400,
            reserved_system=1800,
            safety_margin=500,
        ),
        timeout_seconds=60,
    )
    return skill


def test_real_supervisor_typical_routing_cases():
    config = _live_config()
    supervisor = _bounded_supervisor()
    runtime = build_ai_runtime(config, [supervisor], max_retries=1).runtime
    cases = [
        {
            "id": "resume_explanation",
            "message": "为什么简历里的项目描述不能只写负责系统开发？",
            "page": "resume",
            "skills": ["direct_chat"],
            "snapshot": {"summary": "当前已加载一份简历"},
            "allowed_kinds": {"skill_call"},
            "expected_name": "direct_chat",
        },
        {
            "id": "ambiguous_edit_without_target",
            "message": "帮我改一下这个项目。",
            "page": "resume",
            "skills": [],
            "snapshot": {"summary": "没有选中文字或项目"},
            "allowed_kinds": {"clarification"},
        },
        {
            "id": "selected_resume_rewrite",
            "message": "把选中的这句话写得更专业、简洁一些。",
            "page": "resume",
            "skills": ["text_rewriter"],
            "snapshot": {
                "selected_text": "负责智能求职助手后端开发，完成了一些接口。",
                "surrounding_context": "项目经历：不平智能求职助手。",
                "language": "zh",
            },
            "allowed_kinds": {"skill_call"},
            "expected_name": "text_rewriter",
        },
        {
            "id": "whole_resume_review",
            "message": "当前简历有哪些优缺点？",
            "page": "resume",
            "skills": ["resume_reviewer"],
            "snapshot": {
                "summary": "当前简历已加载",
                "resume_artifact": {
                    "artifact_id": "resume.current", "version": "live:dirty",
                    "source": "editor_unsaved", "is_dirty": True,
                    "content_available": True,
                },
            },
            "allowed_kinds": {"skill_call"},
            "expected_name": "resume_reviewer",
        },
        {
            "id": "cross_page_write_request",
            "message": "删除我简历里的第一段工作经历。",
            "page": "interview-prep",
            "skills": [],
            "snapshot": {"summary": "当前是面试准备页面"},
            "allowed_kinds": {"final_response", "clarification"},
        },
        {
            "id": "multi_step_request_is_bounded",
            "message": "先选三个岗位，再为第一名改简历并生成面试题。",
            "page": "job-radar",
            "skills": [],
            "snapshot": {"summary": "当前展示岗位推荐列表"},
            "allowed_kinds": {"final_response", "clarification"},
        },
    ]

    total_tokens = 0
    observed: list[dict[str, object]] = []
    for case in cases:
        inputs = {
            "message": case["message"],
            "page": case["page"],
            "selected_objects": ["resume.selection"] if case["id"] == "selected_resume_rewrite" else [],
            "available_skills": case["skills"],
            "available_workflows": [],
            "available_actions": [],
            "conversation_summary": "",
            "workspace_snapshot": case["snapshot"],
        }
        result = runtime.execute(
            supervisor.metadata.name,
            inputs,
            provider=config["provider"],
            model=config["model"],
        )
        turn = SupervisorTurn.model_validate(result.structured_output)
        total_tokens += result.usage.total_tokens
        observed.append({
            "case": case["id"], "kind": turn.kind, "name": turn.name,
            "tokens": result.usage.total_tokens,
        })
        assert turn.kind in case["allowed_kinds"]
        if case.get("expected_name"):
            assert turn.name == case["expected_name"]

    print({"routing_cases": observed, "total_tokens": total_tokens})
    assert total_tokens <= 30_000, "routing smoke test exceeded its safety budget"


def test_real_resume_rewrite_creates_pending_proposal_without_applying(tmp_path, monkeypatch):
    config = _live_config()
    monkeypatch.setenv("AI_MEMORY_DB", str(tmp_path / "assistant-live.sqlite3"))
    repository = AssistantRepository(tmp_path / "assistant-live.sqlite3")
    service = AssistantService(repository)
    session = service.create_session("resume", "live-rewrite")["session"]

    result = service.send_message(
        session["id"],
        message="把选中的内容写得更专业并保持事实不变。",
        page="resume",
        workspace_snapshot={
            "selected_text": "负责智能求职助手后端开发，完成了一些接口。",
            "surrounding_context": "项目经历：不平智能求职助手。",
            "language": "zh",
            "version": "live-test-v1",
        },
        selected_objects=["resume.selection"],
        api_key=config["api_key"], provider=config["provider"], model=config["model"],
        base_url=config["base_url"],
    )

    assert result["run"]["status"] == "completed"
    assert result["run"]["effective_mode"] == "direct_skill"
    assert result["run"]["usage"]["total_tokens"] <= 5_000
    proposal = result["proposal"]
    assert proposal is not None
    assert proposal["status"] == "pending", "backend must not apply a resume edit automatically"
    assert proposal["payload"]["original_text"] == "负责智能求职助手后端开发，完成了一些接口。"
    replacement = proposal["payload"]["replacement_text"]
    assert replacement.strip()
    assert replacement != proposal["payload"]["original_text"]
    assert "\ufffd" not in replacement, "provider response contains real Unicode replacement characters"
    print({
        "e2e_mode": result["run"]["effective_mode"],
        "tokens": result["run"]["usage"]["total_tokens"],
        "proposal_status": proposal["status"],
        "replacement_unicode_escape": replacement.encode("unicode_escape").decode("ascii"),
    })


def test_real_direct_chat_is_generated_after_supervisor_routing(tmp_path, monkeypatch):
    config = _live_config()
    monkeypatch.setenv("AI_MEMORY_DB", str(tmp_path / "assistant-chat-live.sqlite3"))
    repository = AssistantRepository(tmp_path / "assistant-chat-live.sqlite3")
    service = AssistantService(repository)
    session = service.create_session("job-radar", "live-direct-chat")["session"]

    result = service.send_message(
        session["id"], message="岗位匹配分代表什么？它等同于拿到面试的概率吗？", page="job-radar",
        workspace_snapshot={
            "language": "zh",
            "summary": "匹配分用于当前岗位候选的相对排序，不是录用概率。",
        },
        context_refs=None,
        api_key=config["api_key"], provider=config["provider"], model=config["model"],
        base_url=config["base_url"],
    )

    print({
        "direct_chat_mode": result["run"].get("effective_mode"),
        "direct_chat_intent": str(result["run"].get("intent") or "").encode("unicode_escape").decode("ascii"),
        "direct_chat_capability": result["assistant_message"]["metadata"].get("capability"),
        "direct_chat_reason": result["assistant_message"]["metadata"].get("reason_code"),
    })
    assert result["run"]["status"] == "completed"
    assert result["assistant_message"]["metadata"]["capability"] == "direct_chat"
    assert result["run"]["effective_mode"] == "chat"
    assert result["assistant_message"]["content"].strip()
    assert "{\"kind\"" not in result["assistant_message"]["content"]
    print({
        "direct_chat_tokens": result["run"]["usage"]["total_tokens"],
        "mode": result["run"]["effective_mode"],
    })


def test_real_whole_resume_review_reads_unsaved_artifact(tmp_path, monkeypatch):
    config = _live_config()
    monkeypatch.setenv("AI_MEMORY_DB", str(tmp_path / "assistant-review-live.sqlite3"))
    repository = AssistantRepository(tmp_path / "assistant-review-live.sqlite3")
    service = AssistantService(repository)
    session = service.create_session("resume", "live-review")["session"]

    result = service.send_message(
        session["id"],
        message="当前简历有哪些优缺点？请按优先级说明。",
        page="resume",
        workspace_snapshot={
            "summary": "当前简历已加载",
            "language": "zh",
            "resume_artifact": {
                "id": "resume.current",
                "version": "live-review:dirty",
                "content_format": "html",
                "source": "editor_unsaved",
                "is_dirty": True,
                "content": (
                    "<h1>测试候选人</h1><h2>项目经历</h2>"
                    "<h3>不平智能求职助手</h3>"
                    "<p>负责 AI Runtime 与 Skill 框架设计，完成上下文预算、缓存和运行观测。</p>"
                    "<p>设计简历事实校验 Harness，保护姓名、教育经历和项目实体绑定。</p>"
                ),
            },
        },
        api_key=config["api_key"], provider=config["provider"], model=config["model"],
        base_url=config["base_url"],
    )

    assert result["run"]["status"] == "completed"
    assert result["run"]["effective_mode"] == "direct_skill"
    assert result["assistant_message"]["metadata"]["capability"] == "resume_reviewer"
    assert result["assistant_message"]["metadata"]["artifact_is_dirty"] is True
    assert result["assistant_message"]["content"].startswith("### 总体评价")
    assert "依据" in result["assistant_message"]["content"]
    assert result["run"]["usage"]["total_tokens"] <= 8_000
    reasoning_events = [
        event for event in result["assistant_message"]["metadata"].get("runtime_events", [])
        if event.get("stage") == "model_reasoning"
    ]
    print({
        "review_mode": result["run"]["effective_mode"],
        "tokens": result["run"]["usage"]["total_tokens"],
        "included_unsaved": result["assistant_message"]["metadata"]["artifact_is_dirty"],
        "reasoning_events": len(reasoning_events),
        "reasoning_characters": reasoning_events[-1].get("reasoning_characters", 0) if reasoning_events else 0,
    })


def test_real_job_recommendation_cases_are_grounded_and_budgeted(tmp_path, monkeypatch):
    config = _live_config()
    monkeypatch.setenv("AI_MEMORY_DB", str(tmp_path / "assistant-job-live.sqlite3"))
    repository = AssistantRepository(tmp_path / "assistant-job-live.sqlite3")
    service = AssistantService(repository)
    jobs = [
        {"id": "agent-sh", "company": "星河科技", "role": "AI Agent开发工程师", "location": "上海", "recruitment_type": "秋招", "match_score": 96, "industry": "互联网", "company_type": "民营企业", "link": "https://example.com/agent-sh"},
        {"id": "llm-hz", "company": "云帆智能", "role": "大模型应用开发工程师", "location": "杭州", "recruitment_type": "正式批", "match_score": 92, "industry": "人工智能", "company_type": "民营企业", "link": "https://example.com/llm-hz"},
        {"id": "rag-bj", "company": "北辰研究院", "role": "RAG算法工程师", "location": "北京", "recruitment_type": "提前批", "match_score": 90, "industry": "科研", "company_type": "科研/事业单位", "link": "https://example.com/rag-bj"},
        {"id": "multimodal-sh", "company": "镜界科技", "role": "多模态算法工程师", "location": "上海", "recruitment_type": "秋招", "match_score": 89, "industry": "人工智能", "company_type": "民营企业", "link": "https://example.com/multimodal-sh"},
        {"id": "python-sz", "company": "深蓝数据", "role": "Python后端工程师", "location": "深圳", "recruitment_type": "正式批", "match_score": 84, "industry": "软件", "company_type": "上市公司", "link": "https://example.com/python-sz"},
        {"id": "cv-sh", "company": "光影智能", "role": "计算机视觉工程师", "location": "上海", "recruitment_type": "实习", "match_score": 82, "industry": "人工智能", "company_type": "民营企业", "link": "https://example.com/cv-sh"},
        {"id": "platform-nj", "company": "江云软件", "role": "AI平台工程师", "location": "南京", "recruitment_type": "秋招", "match_score": 80, "industry": "软件", "company_type": "国企/央企", "link": "https://example.com/platform-nj"},
        {"id": "java-sh", "company": "海岳网络", "role": "Java服务端研发", "location": "上海", "recruitment_type": "正式批", "match_score": 76, "industry": "互联网", "company_type": "上市公司", "link": "https://example.com/java-sh"},
        {"id": "isp-xa", "company": "西境影像", "role": "ISP调优工程师", "location": "西安", "recruitment_type": "秋招", "match_score": 73, "industry": "消费电子", "company_type": "民营企业", "link": "https://example.com/isp-xa"},
        {"id": "ops-bj", "company": "恒稳科技", "role": "桌面运维工程师", "location": "北京", "recruitment_type": "正式批", "match_score": 55, "industry": "IT服务", "company_type": "民营企业", "link": "https://example.com/ops-bj"},
        {"id": "product-gz", "company": "南星产品", "role": "AI产品经理", "location": "广州", "recruitment_type": "秋招", "match_score": 68, "industry": "互联网", "company_type": "民营企业", "link": "https://example.com/product-gz"},
        {"id": "embedded-sz", "company": "芯河电子", "role": "嵌入式开发工程师", "location": "深圳", "recruitment_type": "秋招", "match_score": 65, "industry": "半导体", "company_type": "上市公司", "link": "https://example.com/embedded-sz"},
    ]
    preferences = {
        "target_roles": ["AI Agent开发", "大模型应用开发", "多模态算法"],
        "preferred_locations": ["上海", "杭州"],
        "excluded_keywords": ["运维"],
        "recruitment_types": ["秋招", "提前批", "正式批"],
    }
    cases = [
        ("给我推荐十个最适合我的岗位", 10),
        ("优先上海和AI Agent方向，只推荐三个岗位", 3),
        ("比较当前岗位，给我五个最值得优先投递的选择", 5),
        ("避开运维岗位，推荐四个与大模型或多模态相关的机会", 4),
    ]
    observed = []
    for index, (message, expected_count) in enumerate(cases):
        session = service.create_session("job-radar", f"live-job-{index}")["session"]
        result = service.send_message(
            session["id"], message=message, page="job-radar",
            workspace_snapshot={"language": "zh", "job_preferences": preferences, "job_results": jobs},
            context_refs=["radar.preferences", "radar.results"],
            api_key=config["api_key"], provider=config["provider"], model=config["model"],
            base_url=config["base_url"],
        )
        assert result["run"]["status"] == "completed"
        assert result["assistant_message"]["metadata"]["capability"] == "job_recommender"
        assert result["assistant_message"]["content"].startswith("### 岗位推荐")
        assert result["assistant_message"]["content"].count("｜") == expected_count
        assert result["run"]["usage"]["total_tokens"] <= 12_000
        observed.append({
            "query": message, "count": expected_count,
            "tokens": result["run"]["usage"]["total_tokens"],
            "mode": result["run"]["effective_mode"],
        })
    print({"job_recommendation_cases": observed})
