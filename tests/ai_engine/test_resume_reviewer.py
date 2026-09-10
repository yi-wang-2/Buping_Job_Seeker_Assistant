from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from backend.services.assistant_repository import AssistantRepository
from backend.services.assistant_service import AssistantService
from src.libs.ai_engine.artifact_resolvers import ResumeArtifactResolver
from src.libs.ai_engine.models import TokenUsage
from src.libs.ai_engine.presentation import MarkdownRenderer
from src.libs.ai_engine.providers import GatewayConfig, LLMGateway
from src.libs.ai_engine.runtime import AIRuntime
from src.libs.ai_engine.skills import SkillRegistry, SkillResult
from src.libs.ai_engine.skills.builtin import ResumeReviewerSkill


@dataclass
class FakeResponse:
    content: str
    response_metadata: dict | None = None
    usage_metadata: dict | None = None

    def __post_init__(self) -> None:
        self.response_metadata = {"model_name": "fake"}
        self.usage_metadata = {"input_tokens": 30, "output_tokens": 20, "total_tokens": 50}


class FakeClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def invoke(self, messages):
        return FakeResponse(json.dumps(self.payload, ensure_ascii=False))


def _review_payload(quote: str = "负责智能求职助手后端开发") -> dict:
    return {
        "overall_summary": "项目方向明确，但成果证据不足。",
        "strengths": [{
            "section": "项目经历", "title": "方向明确",
            "analysis": "能够快速说明项目主题。", "evidence_quote": quote,
        }],
        "weaknesses": [{
            "section": "项目经历", "title": "量化不足",
            "analysis": "没有给出规模或结果指标。", "evidence_quote": quote,
        }],
        "priorities": [{
            "priority": "high", "action": "补充可核实成果", "reason": "增强说服力",
        }],
    }


def test_resume_artifact_resolver_reads_unsaved_body_and_removes_editor_noise():
    artifact = ResumeArtifactResolver().resolve({
        "resume_artifact": {
            "id": "resume.current", "version": "3:dirty", "content_format": "html",
            "source": "editor_unsaved", "is_dirty": True,
            "content": "<html><style>.x{}</style><body><h1>易旺</h1><section><h2>项目经历</h2>"
                       "<p>负责智能求职助手后端开发</p></section>"
                       "<button data-editor-only>删除经历</button><script>secret()</script></body></html>",
        },
    })

    assert artifact.is_dirty is True
    assert artifact.version == "3:dirty"
    assert "易旺" in artifact.text
    assert "负责智能求职助手后端开发" in artifact.text
    assert "删除经历" not in artifact.text
    assert "secret" not in artifact.text
    assert artifact.blocks[0].block_id == "resume-header"
    assert artifact.blocks[1].block_id == "section-1"
    assert "负责智能求职助手后端开发" in artifact.blocks[1].text


def test_resume_reviewer_requires_verbatim_evidence():
    registry = SkillRegistry()
    registry.register(ResumeReviewerSkill())
    valid_runtime = AIRuntime(
        LLMGateway(GatewayConfig(), client_factory=lambda _: FakeClient(_review_payload())), registry,
    )
    result = valid_runtime.execute(
        "resume_reviewer",
        {"resume_text": "项目经历\n负责智能求职助手后端开发", "language": "zh"},
        provider="fake", model="fake",
    )
    assert result.structured_output["strengths"][0]["section"] == "整份简历"
    assert result.structured_output["strengths"][0]["block_id"] == "resume-document"
    assert result.presentation is not None
    rendered = MarkdownRenderer.render(result.presentation)
    assert rendered.startswith("### 总体评价\n\n> 项目方向明确")
    assert "### 优点" in rendered
    assert "> 依据：负责智能求职助手后端开发" in rendered
    assert rendered.endswith("也可以让我给出整版修改方案。")

    partial_payload = _review_payload()
    partial_payload["strengths"].append({
        "section": "工作经历", "title": "团队管理", "analysis": "具备管理经验",
        "block_id": "missing", "evidence_quote": "带领20人团队",
    })
    partial_runtime = AIRuntime(
        LLMGateway(GatewayConfig(), client_factory=lambda _: FakeClient(partial_payload)), registry,
    )
    partial = partial_runtime.execute(
        "resume_reviewer",
        {"resume_text": "项目经历\n负责智能求职助手后端开发", "language": "zh"},
        provider="fake", model="fake",
    )
    assert len(partial.structured_output["strengths"]) == 1
    assert partial.structured_output["grounding_status"] == "partially_grounded"
    assert partial.structured_output["grounding_removed_count"] == 1

    drifted_quote = "研究方向：多模态时序预测\n研究内容：多模态、时序预测、图像处理、深度学习"
    repaired_runtime = AIRuntime(
        LLMGateway(
            GatewayConfig(),
            client_factory=lambda _: FakeClient(_review_payload(drifted_quote)),
        ),
        registry,
    )
    repaired = repaired_runtime.execute(
        "resume_reviewer",
        {"resume_text": "教育经历\n研究方向：多模态、时序预测、图像处理、深度学习"},
        provider="fake", model="fake",
    )
    assert repaired.structured_output["strengths"][0]["evidence_quote"] == (
        "研究方向：多模态、时序预测、图像处理、深度学习"
    )

    invalid_runtime = AIRuntime(
        LLMGateway(
            GatewayConfig(),
            client_factory=lambda _: FakeClient(_review_payload("带领 20 人团队")),
        ),
        registry,
    )
    with pytest.raises(ValueError, match="evidence"):
        invalid_runtime.execute(
            "resume_reviewer", {"resume_text": "项目经历\n负责智能求职助手后端开发"},
            provider="fake", model="fake",
        )


def test_assistant_whole_resume_review_uses_artifact_without_requiring_selection(tmp_path, monkeypatch):
    class FakeRuntime:
        def execute(self, skill_name, inputs, **kwargs):
            if skill_name == "assistant_supervisor":
                assert inputs["workspace_snapshot"]["resume_artifact"]["content_available"] is True
                assert "content" not in inputs["workspace_snapshot"]["resume_artifact"]
                return SkillResult(
                    content="route",
                    structured_output={
                        "kind": "skill_call", "intent": "review_resume", "target_refs": ["resume.current"],
                        "name": "resume_reviewer", "arguments": {}, "response": "",
                        "reason_code": "whole_resume_review",
                    },
                    usage=TokenUsage(10, 5, 15),
                )
            assert skill_name == "resume_reviewer"
            assert "未保存版本中的新内容" in inputs["resume_text"]
            assert inputs["resume_blocks"][0]["block_id"] == "resume-document"
            stream_sink = kwargs.get("stream_event_sink")
            assert stream_sink is not None
            stream_sink({"kind": "thinking", "reasoning_characters": 240, "text_characters": 0})
            stream_sink({
                "kind": "text_started", "reasoning_characters": 240,
                "text_characters": 8, "reasoning_seen": True,
            })
            stream_sink({
                "kind": "stream_completed", "reasoning_characters": 240,
                "text_characters": 80, "reasoning_seen": True,
            })
            return SkillResult(
                content="review", structured_output=_review_payload("未保存版本中的新内容"),
                usage=TokenUsage(30, 20, 50),
            )

    monkeypatch.setattr(
        "backend.services.assistant_service.build_ai_runtime",
        lambda *args, **kwargs: SimpleNamespace(runtime=FakeRuntime()),
    )
    repository = AssistantRepository(tmp_path / "assistant.sqlite3")
    service = AssistantService(repository)
    session = service.create_session("resume", "current-resume")["session"]
    runtime_events = []
    result = service.send_message(
        session["id"], message="当前简历有哪些优缺点？", page="resume",
        workspace_snapshot={
            "summary": "当前简历已加载", "language": "zh",
            "resume_artifact": {
                "id": "resume.current", "version": "4:dirty", "content_format": "html",
                "source": "editor_unsaved", "is_dirty": True,
                "content": "<h2>项目经历</h2><p>未保存版本中的新内容</p>",
            },
        },
        context_refs=["resume.current"],
        api_key="test", provider="fake", model="fake",
        event_sink=runtime_events.append,
    )

    assert result["run"]["status"] == "completed"
    assert result["run"]["effective_mode"] == "direct_skill"
    assert result["proposal"] is None
    assert result["assistant_message"]["content"].startswith("### 总体评价")
    assert "### 优点" in result["assistant_message"]["content"]
    assert result["assistant_message"]["metadata"]["artifact_is_dirty"] is True
    assert result["user_message"]["metadata"]["context_refs"] == ["resume.current"]
    assert result["assistant_message"]["metadata"]["context_refs"] == ["resume.current"]
    assert "resume_body_resolved" in result["assistant_message"]["metadata"]["context_events"]
    reasoning_events = [event for event in runtime_events if event["stage"] == "model_reasoning"]
    assert len(reasoning_events) == 2
    assert reasoning_events[-1]["status"] == "completed"
    assert reasoning_events[-1]["private_reasoning_redacted"] is True
    assert [event["stage"] for event in runtime_events] == [
        "request_accepted", "workspace_context", "run_started", "supervisor", "supervisor", "policy",
        "artifact", "artifact", "skill", "model_reasoning", "model_reasoning", "skill",
        "skill", "harness", "completed",
    ]


def test_empty_resume_artifact_is_not_advertised_to_supervisor():
    snapshot = AssistantService._safe_snapshot({
        "summary": "当前尚未加载简历",
        "resume_artifact": {"id": "resume.current", "content": ""},
    })
    assert snapshot["resume_artifact"]["content_available"] is False


def test_explicit_context_refs_scope_workspace_snapshot():
    snapshot = {
        "language": "zh",
        "selected_text": "选中文字",
        "surrounding_context": "前后文",
        "job_description": "AI Agent 工程师",
        "resume_artifact": {"content": "完整简历"},
    }

    jd_only = AssistantService._scope_snapshot(
        snapshot, ["resume.job_description"], explicit=True,
    )
    assert jd_only == {"language": "zh", "job_description": "AI Agent 工程师"}
    assert AssistantService._scope_snapshot(snapshot, [], explicit=True) == {"language": "zh"}
    assert AssistantService._scope_snapshot(snapshot, [], explicit=False) == snapshot


def test_job_radar_stats_are_separate_from_limited_result_sample():
    snapshot = AssistantService._safe_snapshot({
        "language": "zh",
        "job_radar_stats": {"total": 321, "companies": 87, "favorites": 4},
        "job_results_meta": {
            "matching_results": 200, "sample_size": 20, "is_sample": True, "scene": "general",
        },
        "job_results": [{"id": str(index), "company": f"公司{index}"} for index in range(25)],
    })

    assert snapshot["job_radar_stats"]["companies"] == 87
    assert len(snapshot["job_results"]) == 20
    assert snapshot["job_results_meta"]["is_sample"] is True
    assert AssistantService._scope_snapshot(snapshot, ["radar.stats"], explicit=True) == {
        "language": "zh", "job_radar_stats": snapshot["job_radar_stats"],
    }


def test_uploaded_document_is_session_scoped_and_available_to_supervisor(tmp_path, monkeypatch):
    class AttachmentRuntime:
        def execute(self, skill_name, inputs, **kwargs):
            assert skill_name == "assistant_supervisor"
            documents = inputs["workspace_snapshot"]["uploaded_documents"]
            assert documents[0]["filename"] == "需求说明.txt"
            assert "Agent Runtime" in documents[0]["content"]
            return SkillResult(
                content="route", structured_output={
                    "kind": "final_response", "intent": "summarize_document", "target_refs": [],
                    "name": None, "arguments": {}, "response": "### 文档摘要\n\n该文档介绍 Agent Runtime。",
                    "follow_up": "", "reason_code": "document_context",
                }, usage=TokenUsage(8, 4, 12),
            )

    monkeypatch.setattr(
        "backend.services.assistant_service.build_ai_runtime",
        lambda *args, **kwargs: SimpleNamespace(runtime=AttachmentRuntime()),
    )
    service = AssistantService(AssistantRepository(tmp_path / "attachments.sqlite3"))
    session = service.create_session("resume", "attachment-test")["session"]
    attachment = service.upload_attachment(
        session["id"], filename="需求说明.txt", content_type="text/plain",
        raw="本文介绍 Agent Runtime 的上下文管理。".encode("utf-8"),
    )
    ref = f"attachment:{attachment['id']}"

    result = service.send_message(
        session["id"], message="总结上传的文档", page="resume",
        workspace_snapshot={"language": "zh"}, context_refs=[ref],
        context_labels={ref: "需求说明.txt"},
        api_key="test", provider="fake", model="fake",
    )

    assert result["run"]["status"] == "completed"
    assert result["user_message"]["metadata"]["context_refs"] == [ref]
    assert result["user_message"]["metadata"]["context_labels"] == {ref: "需求说明.txt"}
    assert result["assistant_message"]["metadata"]["context_refs"] == [ref]
    assert service.create_session("resume", "attachment-test")["attachments"][0]["filename"] == "需求说明.txt"


def test_assistant_resume_generation_creates_confirmable_workflow_proposal(tmp_path, monkeypatch):
    class WorkflowRuntime:
        def execute(self, skill_name, inputs, **kwargs):
            assert skill_name == "assistant_supervisor"
            assert inputs["available_workflows"] == ["generate_resume"]
            return SkillResult(
                content="route", structured_output={
                    "kind": "workflow_call", "intent": "generate_resume", "target_refs": ["resume.workspace"],
                    "name": "generate_resume", "arguments": {}, "response": "", "follow_up": "",
                    "reason_code": "explicit_generation_request",
                }, usage=TokenUsage(8, 4, 12),
            )

    monkeypatch.setattr(
        "backend.services.assistant_service.build_ai_runtime",
        lambda *args, **kwargs: SimpleNamespace(runtime=WorkflowRuntime()),
    )
    service = AssistantService(AssistantRepository(tmp_path / "workflow.sqlite3"))
    session = service.create_session("resume", "workflow-test")["session"]
    result = service.send_message(
        session["id"], message="按当前设置生成简历", page="resume",
        workspace_snapshot={
            "language": "zh", "version": "3:current", "job_description": "AI Agent 工程师",
            "resume_generation_options": {"generation_mode": "new", "target_pages": 2, "style_name": "standard"},
        }, api_key="test", provider="fake", model="fake",
    )

    assert result["run"]["effective_mode"] == "fixed_workflow"
    assert result["proposal"]["proposal_type"] == "resume_generation_request"
    assert result["proposal"]["payload"]["target_pages"] == 2
    assert result["proposal"]["status"] == "pending"


def test_historical_resume_context_is_path_safe_and_prefers_saved_html(tmp_path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    (output / "产品经理简历.pdf").write_bytes(b"placeholder")
    (output / "产品经理简历.html").write_text(
        "<html><body><h1>历史简历姓名</h1><script>ignore()</script></body></html>",
        encoding="utf-8",
    )
    monkeypatch.setattr("backend.services.assistant_service.RESUME_OUTPUT_FOLDER", output)
    ref = "resume.history:产品经理简历.pdf"

    assert AssistantService._normalize_context_refs([ref, "resume.history:../secret.pdf"]) == [ref]
    documents = AssistantService._load_history_resume_documents([ref])
    assert documents[ref]["filename"] == "产品经理简历.pdf"
    assert "历史简历姓名" in documents[ref]["content"]
    assert "ignore" not in documents[ref]["content"]


def test_resume_review_retries_validation_once_then_succeeds(tmp_path, monkeypatch):
    class RetryRuntime:
        review_calls = 0

        def execute(self, skill_name, inputs, **kwargs):
            if skill_name == "assistant_supervisor":
                return SkillResult(
                    content="route", structured_output={
                        "kind": "skill_call", "intent": "review_resume", "target_refs": [],
                        "name": "resume_reviewer", "arguments": {}, "response": "",
                        "reason_code": "whole_resume_review",
                    }, usage=TokenUsage(5, 2, 7),
                )
            self.review_calls += 1
            if self.review_calls == 1:
                error = ValueError("ungrounded")
                error.skill_usage = TokenUsage(20, 10, 30)
                raise error
            assert "上一次输出未通过" in inputs["request"]
            return SkillResult(
                content="review", structured_output=_review_payload("真实项目内容"),
                usage=TokenUsage(25, 15, 40),
            )

    runtime = RetryRuntime()
    monkeypatch.setattr(
        "backend.services.assistant_service.build_ai_runtime",
        lambda *args, **kwargs: SimpleNamespace(runtime=runtime),
    )
    service = AssistantService(AssistantRepository(tmp_path / "retry.sqlite3"))
    session = service.create_session("resume", "retry")["session"]
    result = service.send_message(
        session["id"], message="分析当前简历", page="resume",
        workspace_snapshot={"resume_artifact": {
            "content": "<p>真实项目内容</p>", "content_format": "html", "version": "v1",
        }},
        api_key="test", provider="fake", model="fake",
    )

    assert result["run"]["status"] == "completed"
    assert result["run"]["usage"]["total_tokens"] == 77
    assert result["assistant_message"]["metadata"]["grounding_retry"] is True
    assert "review_grounding_retried" in result["assistant_message"]["metadata"]["context_events"]


def test_text_rewrite_proposal_binds_artifact_hash_and_version(tmp_path, monkeypatch):
    html = "<html><body><p>负责后端开发</p></body></html>"

    class RewriteRuntime:
        def execute(self, skill_name, inputs, **kwargs):
            if skill_name == "assistant_supervisor":
                return SkillResult(
                    content="route", structured_output={
                        "kind": "skill_call", "intent": "rewrite", "target_refs": ["resume.selection"],
                        "name": "text_rewriter", "arguments": {"mode": "more_professional"},
                        "response": "", "reason_code": "single_explicit_edit",
                    }, usage=TokenUsage(5, 2, 7),
                )
            return SkillResult(content="负责后端服务设计与开发", usage=TokenUsage(20, 8, 28))

    monkeypatch.setattr(
        "backend.services.assistant_service.build_ai_runtime",
        lambda *args, **kwargs: SimpleNamespace(runtime=RewriteRuntime()),
    )
    service = AssistantService(AssistantRepository(tmp_path / "rewrite.sqlite3"))
    session = service.create_session("resume", "rewrite")["session"]
    result = service.send_message(
        session["id"], message="润色选中文字", page="resume",
        workspace_snapshot={
            "selected_text": "负责后端开发", "version": "v2:dirty",
            "resume_artifact": {
                "content": html, "content_format": "html", "version": "v2:dirty",
            },
        },
        selected_objects=["resume.selection"], api_key="test", provider="fake", model="fake",
    )

    proposal = result["proposal"]
    assert proposal["target_version"] == "v2:dirty"
    assert proposal["payload"]["base_artifact_hash"] == hashlib.sha256(html.encode()).hexdigest()
    assert proposal["payload"]["original_text_hash"] == hashlib.sha256("负责后端开发".encode()).hexdigest()


def test_resume_review_degrades_without_exposing_ungrounded_findings(tmp_path, monkeypatch):
    class AlwaysInvalidRuntime:
        def execute(self, skill_name, inputs, **kwargs):
            if skill_name == "assistant_supervisor":
                return SkillResult(
                    content="route", structured_output={
                        "kind": "skill_call", "intent": "review_resume", "target_refs": [],
                        "name": "resume_reviewer", "arguments": {}, "response": "",
                        "reason_code": "whole_resume_review",
                    }, usage=TokenUsage(5, 2, 7),
                )
            error = ValueError("invented evidence: 带领20人团队")
            error.skill_usage = TokenUsage(10, 5, 15)
            raise error

    monkeypatch.setattr(
        "backend.services.assistant_service.build_ai_runtime",
        lambda *args, **kwargs: SimpleNamespace(runtime=AlwaysInvalidRuntime()),
    )
    service = AssistantService(AssistantRepository(tmp_path / "degraded.sqlite3"))
    session = service.create_session("resume", "degraded")["session"]
    result = service.send_message(
        session["id"], message="分析当前简历", page="resume",
        workspace_snapshot={"resume_artifact": {
            "content": "<p>负责后端开发</p>", "content_format": "html", "version": "v1",
        }},
        api_key="test", provider="fake", model="fake",
    )

    assert result["run"]["status"] == "completed"
    assert result["run"]["usage"]["total_tokens"] == 37
    assert "带领20人团队" not in result["assistant_message"]["content"]
    assert "已隐藏" in result["assistant_message"]["content"]
    assert result["assistant_message"]["metadata"]["grounding_status"] == "degraded"


def test_text_rewrite_hard_fact_violation_creates_no_proposal(tmp_path, monkeypatch):
    class UnsafeRewriteRuntime:
        def execute(self, skill_name, inputs, **kwargs):
            if skill_name == "assistant_supervisor":
                return SkillResult(
                    content="route", structured_output={
                        "kind": "skill_call", "intent": "rewrite", "target_refs": [],
                        "name": "text_rewriter", "arguments": {"mode": "more_quantified"},
                        "response": "", "reason_code": "single_explicit_edit",
                    }, usage=TokenUsage(5, 2, 7),
                )
            return SkillResult(content="负责后端开发，性能提升80%", usage=TokenUsage(20, 8, 28))

    monkeypatch.setattr(
        "backend.services.assistant_service.build_ai_runtime",
        lambda *args, **kwargs: SimpleNamespace(runtime=UnsafeRewriteRuntime()),
    )
    service = AssistantService(AssistantRepository(tmp_path / "unsafe-rewrite.sqlite3"))
    session = service.create_session("resume", "unsafe-rewrite")["session"]
    result = service.send_message(
        session["id"], message="量化这句话", page="resume",
        workspace_snapshot={
            "selected_text": "负责后端开发",
            "resume_artifact": {
                "content": "<p>负责后端开发</p>", "content_format": "html", "version": "v1",
            },
        },
        selected_objects=["resume.selection"], api_key="test", provider="fake", model="fake",
    )

    assert result["proposal"] is None
    assert "没有被修改" in result["assistant_message"]["content"]
    assert result["assistant_message"]["metadata"]["mutation_status"] == "rejected"
