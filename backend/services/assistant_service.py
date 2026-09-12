from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

from pydantic import ValidationError

from backend.services.ai_runtime_service import build_ai_runtime
from backend.services.ai_skill_service import _resolve_config
from backend.services.assistant_repository import AssistantRepository
from backend.services.job_radar_query_service import execute_job_radar_query
from src.libs.ai_engine.artifact_resolvers import ResumeArtifactResolver
from src.libs.ai_engine.assistant import (
    AssistantController,
    AssistantSupervisorSkill,
    AssistantTurnPresenter,
    DispatchInput,
    PAGE_CAPABILITIES,
    SupervisorTurn,
)
from src.libs.ai_engine.observability import JsonlTraceSink
from src.libs.ai_engine.harness import validate_grounded_text
from src.libs.ai_engine.presentation.service import ensure_formatted_markdown, render_skill_result
from src.libs.ai_engine.presentation import MarkdownRenderer
from src.libs.ai_engine.skills.builtin import DirectChatSkill, JobRecommenderSkill, ResumeReviewerSkill, TextRewriterSkill
from src.libs.resume_and_cover_builder.document_parser import extract_text


IMPLEMENTED_SKILLS = {
    "resume": {"direct_chat", "resume_reviewer", "text_rewriter"},
    "interview-prep": {"direct_chat"},
    "ai-coding": {"direct_chat"},
    "job-radar": {"direct_chat", "job_recommender", "job_radar_query"},
}
REWRITE_MODES = {"more_quantified", "more_professional", "more_concise", "fix_grammar"}
ATTACHMENT_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".html", ".htm", ".tex", ".yaml", ".yml"}
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_STORED_ATTACHMENT_CHARACTERS = 200_000
MAX_CONTEXT_ATTACHMENT_CHARACTERS = 40_000
RESUME_OUTPUT_FOLDER = Path("data_folder/output")


class AssistantRunCancelled(RuntimeError):
    """Raised at cooperative cancellation boundaries in an assistant run."""


class AssistantService:
    def __init__(self, repository: AssistantRepository | None = None) -> None:
        self.repository = repository or AssistantRepository()
        self.controller = AssistantController(max_steps=5, max_replans=1, max_tokens=12000, timeout_seconds=180)

    def create_session(self, workspace_type: str, workspace_object_id: str = "default",
                       title: str = "") -> dict[str, Any]:
        session = self.repository.get_or_create_session(workspace_type, workspace_object_id, title=title)
        return {"session": session, "messages": self.repository.list_messages(session["id"]),
                "proposals": self.repository.list_actionable_proposals(session["id"]),
                "attachments": self.repository.list_attachments(session["id"]),
                "active_runs": self.repository.list_active_runs(session["id"])}

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        session = self.repository.get_session(session_id)
        if not session:
            return None
        return {"session": session, "messages": self.repository.list_messages(session_id),
                "proposals": self.repository.list_actionable_proposals(session_id),
                "attachments": self.repository.list_attachments(session_id),
                "active_runs": self.repository.list_active_runs(session_id)}

    def upload_attachment(
        self, session_id: str, *, filename: str, content_type: str, raw: bytes,
    ) -> dict[str, Any]:
        if not self.repository.get_session(session_id):
            raise KeyError("Assistant session not found")
        safe_name = Path(filename or "document.txt").name
        extension = Path(safe_name).suffix.lower()
        if extension not in ATTACHMENT_EXTENSIONS:
            raise ValueError("Unsupported document type")
        if not raw:
            raise ValueError("Uploaded document is empty")
        if len(raw) > MAX_ATTACHMENT_BYTES:
            raise ValueError("Document exceeds the 10 MB limit")
        try:
            content = extract_text(safe_name, raw).strip()
        except Exception as exc:
            raise ValueError(f"Failed to extract document text: {exc}") from exc
        if not content:
            raise ValueError("No readable text was found in the document")
        return self.repository.create_attachment(
            session_id, filename=safe_name, mime_type=content_type or "application/octet-stream",
            size_bytes=len(raw), content_text=content[:MAX_STORED_ATTACHMENT_CHARACTERS],
        )

    def send_message(
        self, session_id: str, *, message: str, page: str,
        workspace_snapshot: dict[str, Any] | None = None,
        selected_objects: list[str] | None = None,
        context_refs: list[str] | None = None,
        context_labels: dict[str, str] | None = None,
        api_key: str = "", provider: str = "", model: str = "", base_url: str = "",
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        runtime_events: list[dict[str, Any]] = []

        def emit(stage: str, detail: str, status: str = "completed", **metadata: Any) -> None:
            event = {
                "stage": stage,
                "detail": detail,
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **metadata,
            }
            runtime_events.append(event)
            if event_sink:
                event_sink(event)

        if not self.repository.get_session(session_id):
            raise KeyError("Assistant session not found")
        emit("request_accepted", "已接收请求")
        normalized_context_refs = self._normalize_context_refs(context_refs)
        attachment_ids = [ref.split(":", 1)[1] for ref in normalized_context_refs if ref.startswith("attachment:")]
        attachments = self.repository.get_attachments(session_id, attachment_ids)
        valid_attachment_refs = {f"attachment:{item['id']}" for item in attachments}
        history_documents = self._load_history_resume_documents(normalized_context_refs)
        normalized_context_refs = [
            ref for ref in normalized_context_refs
            if (
                (not ref.startswith("attachment:") or ref in valid_attachment_refs)
                and (not ref.startswith("resume.history:") or ref in history_documents)
            )
        ]
        normalized_context_labels = {
            ref: str((context_labels or {}).get(ref) or "")[:160]
            for ref in normalized_context_refs
            if str((context_labels or {}).get(ref) or "").strip()
        }
        raw_snapshot = self._scope_snapshot(
            workspace_snapshot or {}, normalized_context_refs, explicit=context_refs is not None,
        )
        if attachments or history_documents:
            remaining = MAX_CONTEXT_ATTACHMENT_CHARACTERS
            documents = []
            attachments_by_ref = {f"attachment:{item['id']}": item for item in attachments}
            for ref in normalized_context_refs:
                if remaining <= 0:
                    break
                if ref in attachments_by_ref:
                    source = attachments_by_ref[ref]
                    full_text = str(source["content_text"])
                    document_id = source["id"]
                    filename = source["filename"]
                    document_type = "uploaded_document"
                elif ref in history_documents:
                    source = history_documents[ref]
                    full_text = source["content"]
                    document_id = ref
                    filename = source["filename"]
                    document_type = "historical_resume"
                else:
                    continue
                text = full_text[:remaining]
                documents.append({
                    "id": document_id, "filename": filename, "document_type": document_type,
                    "content": text, "truncated": len(text) < len(full_text),
                })
                remaining -= len(text)
            raw_snapshot["uploaded_documents"] = documents
        artifact_resolver = ResumeArtifactResolver()
        snapshot = self._safe_snapshot(raw_snapshot, artifact_resolver)
        emit(
            "workspace_context",
            f"已加载 {len(normalized_context_refs)} 项上下文" if context_refs is not None else "已读取当前页面状态",
            artifact_available=bool(snapshot.get("resume_artifact", {}).get("content_available")),
            context_refs=normalized_context_refs,
        )
        selected_objects = list(selected_objects or [])[:20]
        if context_refs is not None and "resume.selection" not in normalized_context_refs:
            selected_objects = [item for item in selected_objects if item != "resume.selection"]
        user_message = self.repository.add_message(
            session_id, "user", message, metadata={
                "context_refs": normalized_context_refs, "context_labels": normalized_context_labels,
            },
        )
        run = self.repository.create_run(session_id, page)
        emit("run_started", "已创建可追踪的助手运行", run_id=run["id"])

        def check_cancelled() -> None:
            if self.repository.is_cancel_requested(run["id"]):
                raise AssistantRunCancelled("Run cancelled by user")

        check_cancelled()
        config = _resolve_config(api_key, provider, model, base_url)
        if not config["api_key"] and config["provider"].lower() != "ollama":
            emit("failed", "缺少可用的模型 API Key", "failed")
            return self._fail(
                run, user_message, "API key is required", "missing_api_key",
                runtime_events=runtime_events,
            )

        supervisor_skill = AssistantSupervisorSkill()
        text_skill = TextRewriterSkill()
        review_skill = ResumeReviewerSkill()
        job_recommender_skill = JobRecommenderSkill()
        direct_chat_skill = DirectChatSkill()
        bundle = build_ai_runtime(
            config, [supervisor_skill, text_skill, review_skill, job_recommender_skill, direct_chat_skill],
            trace_sink=JsonlTraceSink(),
        )
        capabilities = PAGE_CAPABILITIES.get(page)
        implemented = IMPLEMENTED_SKILLS.get(page, set())
        available_skills = sorted((set(capabilities.skills) if capabilities else set()) & implemented)
        if not snapshot.get("selected_text"):
            available_skills = [name for name in available_skills if name != "text_rewriter"]
        if not snapshot.get("resume_artifact", {}).get("content_available"):
            available_skills = [name for name in available_skills if name != "resume_reviewer"]
        recent = self.repository.list_messages(session_id, limit=8)
        conversation_summary = "\n".join(
            f"{item['role']}: {item['content'][:600]}" for item in recent[:-1]
        )
        supervisor_inputs = {
            "message": message,
            "page": page,
            "selected_objects": selected_objects,
            "available_skills": available_skills,
            "available_workflows": sorted(capabilities.workflows) if capabilities else [],
            "available_actions": sorted(capabilities.actions) if capabilities else [],
            "conversation_summary": conversation_summary,
            "workspace_snapshot": snapshot,
        }
        supervisor_usage: dict[str, int] = {}
        execution_metadata: dict[str, Any] = {
            "context_events": ["page_state_read"],
            "context_refs": normalized_context_refs,
            "context_labels": normalized_context_labels,
        }

        def supervise(observations: list[dict[str, Any]] | None = None) -> SupervisorTurn:
            check_cancelled()
            emit("supervisor", "正在根据执行结果重新规划" if observations else "正在判断意图和执行方式", "running")
            call_inputs = {**supervisor_inputs, "observations": observations or []}
            try:
                result = bundle.runtime.execute(
                    supervisor_skill.metadata.name, call_inputs, provider=config["provider"],
                    model=config["model"], session_id=session_id,
                )
                call_usage = self._usage(result)
            except (json.JSONDecodeError, ValidationError) as first_error:
                failed_usage = self._exception_usage(first_error)
                emit("supervisor_retry", "路由结果格式不完整，正在进行一次受控重试", "running")
                result = bundle.runtime.execute(
                    supervisor_skill.metadata.name, call_inputs, provider=config["provider"],
                    model=config["model"], session_id=session_id,
                )
                call_usage = self._sum_usage(failed_usage, self._usage(result))
                emit("supervisor_retry", "路由结果已恢复为有效结构")
            supervisor_usage.update(self._sum_usage(supervisor_usage, call_usage))
            turn = SupervisorTurn.model_validate(result.structured_output)
            check_cancelled()
            if turn.plan:
                emit("plan", "已生成执行计划", plan=turn.plan)
            emit(
                "supervisor", "已确定执行方式", kind=turn.kind,
                capability=turn.name or "direct_response",
            )
            return turn

        def execute(turn: SupervisorTurn) -> dict[str, Any]:
            check_cancelled()
            emit("policy", "页面权限与执行范围校验通过", capability=turn.name or "")
            if turn.kind == "skill_call" and turn.name == "job_radar_query":
                emit("tool", "正在查询完整岗位库", "running", capability=turn.name)
                query_result = execute_job_radar_query(turn.arguments)
                self.repository.record_step(
                    run["id"], skill_name=turn.name, inputs=turn.arguments,
                    status="completed", usage={}, observation={
                        "scope": query_result["scope"],
                        "total_count": query_result["total_count"],
                        "returned_count": query_result["returned_count"],
                        "truncated": query_result["truncated"],
                    },
                )
                emit(
                    "tool", f"岗位库查询完成，共匹配 {query_result['total_count']} 条",
                    capability=turn.name, truncated=query_result["truncated"],
                )
                answer_inputs = {
                    "message": message,
                    "page": page,
                    "workspace_context": {
                        "job_radar_query_result": query_result,
                        "query_result_is_authoritative": True,
                    },
                    "conversation_summary": conversation_summary,
                    "language": "en" if snapshot.get("language") == "en" else "zh",
                }
                result = bundle.runtime.execute(
                    direct_chat_skill.metadata.name, answer_inputs, provider=config["provider"],
                    model=config["model"], session_id=session_id,
                )
                usage = self._usage(result)
                emit("skill", "已根据岗位库查询结果生成回答", capability="direct_chat")
                return {"content": render_skill_result(direct_chat_skill, result, answer_inputs), "usage": usage}
            if turn.kind == "skill_call" and turn.name == "direct_chat":
                inputs = {
                    "message": message,
                    "page": page,
                    "workspace_context": snapshot,
                    "conversation_summary": conversation_summary,
                    "language": "en" if snapshot.get("language") == "en" else "zh",
                }
                emit("skill", "正在结合已附带上下文组织回答", "running", capability=turn.name)
                result = bundle.runtime.execute(
                    direct_chat_skill.metadata.name, inputs, provider=config["provider"],
                    model=config["model"], session_id=session_id,
                )
                usage = self._usage(result)
                self.repository.record_step(
                    run["id"], skill_name=turn.name,
                    inputs={
                        "page": page,
                        "workspace_keys": sorted(snapshot),
                        "has_conversation_summary": bool(conversation_summary),
                    },
                    status="completed", usage=usage,
                    observation={"response_generated": True, "read_only": True},
                )
                emit("skill", "普通问答已生成", capability=turn.name)
                return {"content": render_skill_result(direct_chat_skill, result, inputs), "usage": usage}
            if turn.kind == "workflow_call" and turn.name == "generate_resume":
                options = dict(snapshot.get("resume_generation_options") or {})
                proposal = self.repository.create_proposal(
                    run["id"], proposal_type="resume_generation_request",
                    target_ref="resume.workspace", target_version=str(snapshot.get("version") or "current"),
                    payload={"workflow": "generate_resume", "generation_mode": options.get("generation_mode", "new"),
                             "target_pages": options.get("target_pages", 1), "style_name": options.get("style_name", ""),
                             "job_description_attached": bool(snapshot.get("job_description"))}, risk="medium",
                )
                self.repository.record_step(run["id"], skill_name="workflow:generate_resume", inputs=options,
                                            status="completed", usage={}, observation={"proposal_id": proposal["id"]})
                emit("workflow", "已准备简历生成工作流，等待确认")
                return {"proposal": proposal, "usage": {}}
            if turn.kind == "workflow_call" and turn.name == "prepare_interview":
                options = dict(snapshot.get("interview_generation_options") or {})
                if not snapshot.get("job_description"):
                    raise ValueError("Job description is required before preparing an interview")
                proposal = self.repository.create_proposal(
                    run["id"], proposal_type="interview_preparation_request",
                    target_ref="interview-prep.workspace", target_version=str(snapshot.get("version") or "current"),
                    payload={"workflow": "prepare_interview", "interview_type": options.get("interview_type", "综合面试"),
                             "question_count": options.get("question_count", 10)}, risk="low",
                )
                self.repository.record_step(run["id"], skill_name="workflow:prepare_interview", inputs=options,
                                            status="completed", usage={}, observation={"proposal_id": proposal["id"]})
                emit("workflow", "已准备面试准备工作流，等待确认")
                return {"proposal": proposal, "usage": {}}
            if turn.kind == "action_proposal" and turn.name in {"favorite_job", "not_interested_job", "track_job"}:
                job_id = str(turn.arguments.get("job_id") or "")
                jobs = list(snapshot.get("job_results") or [])
                job = next((item for item in jobs if str(item.get("id")) == job_id), None)
                if not job:
                    raise ValueError("The selected job is not present in the current workspace snapshot")
                proposal = self.repository.create_proposal(
                    run["id"], proposal_type="job_radar_action", target_ref=f"job:{job_id}",
                    target_version=hashlib.sha256(self.repository._json(job).encode("utf-8")).hexdigest(),
                    payload={"action": turn.name, "job": job},
                    risk="medium" if turn.name == "track_job" else "low",
                )
                self.repository.record_step(run["id"], skill_name=f"action:{turn.name}", inputs={"job_id": job_id},
                                            status="completed", usage={}, observation={"proposal_id": proposal["id"]})
                emit("proposal", "已生成岗位操作 Proposal，等待确认")
                return {"proposal": proposal, "usage": {}}
            if turn.kind == "skill_call" and turn.name == "job_recommender":
                jobs = list(snapshot.get("job_results") or [])
                if not jobs:
                    raise ValueError("当前岗位结果为空，请先同步或调整筛选条件")
                try:
                    limit = max(1, min(20, int(turn.arguments.get("limit") or 10)))
                except (TypeError, ValueError):
                    limit = 10
                inputs = {
                    "query": message,
                    "preferences": dict(snapshot.get("job_preferences") or {}),
                    "jobs": jobs,
                    "limit": min(limit, len(jobs)),
                    "language": "en" if snapshot.get("language") == "en" else "zh",
                }
                emit("skill", "正在根据求职偏好比较当前岗位", "running", capability=turn.name)
                result = bundle.runtime.execute(
                    job_recommender_skill.metadata.name, inputs, provider=config["provider"],
                    model=config["model"], session_id=session_id,
                )
                usage = self._usage(result)
                self.repository.record_step(
                    run["id"], skill_name=turn.name,
                    inputs={"candidate_count": len(jobs), "limit": inputs["limit"]},
                    status="completed", usage=usage,
                    observation={
                        "recommended_job_ids": [
                            item.get("job_id") for item in (result.structured_output or {}).get("recommendations", [])
                        ],
                    },
                )
                emit("harness", "推荐结果中的岗位 ID 已与当前岗位库核验")
                emit("skill", "岗位推荐已生成", capability=turn.name)
                return {"content": render_skill_result(job_recommender_skill, result, inputs), "usage": usage}
            if turn.kind != "skill_call" or turn.name not in {"text_rewriter", "resume_reviewer"}:
                raise PermissionError("This capability is not enabled in the first assistant release")
            if turn.name == "resume_reviewer":
                emit("artifact", "正在解析当前简历正文", "running")
                artifact = artifact_resolver.resolve(raw_snapshot)
                emit(
                    "artifact", f"已解析当前简历，共 {artifact.section_count} 个内容块",
                    artifact_version=artifact.version, is_dirty=artifact.is_dirty,
                )
                inputs = {
                    "resume_text": artifact.text,
                    "resume_blocks": [
                        {"block_id": block.block_id, "section": block.section, "text": block.text}
                        for block in artifact.blocks
                    ],
                    "request": message,
                    "language": "en" if snapshot.get("language") == "en" else "zh",
                    "artifact_id": artifact.artifact_id,
                    "artifact_version": artifact.version,
                }
                failed_usage: dict[str, int] = {}

                def reviewer_stream_sink() -> Callable[[dict[str, Any]], None]:
                    state = {"last_reported": 0, "reasoning_seen": False, "reasoning_done": False}

                    def publish_model_event(event: dict[str, Any]) -> None:
                        kind = event.get("kind")
                        reasoning_characters = int(event.get("reasoning_characters") or 0)
                        if kind == "thinking":
                            state["reasoning_seen"] = True
                            if reasoning_characters - int(state["last_reported"]) >= 200:
                                state["last_reported"] = reasoning_characters
                                emit(
                                    "model_reasoning",
                                    f"模型正在分析，已接收 {reasoning_characters} 个推理字符",
                                    "running",
                                    reasoning_characters=reasoning_characters,
                                    private_reasoning_redacted=True,
                                )
                        elif kind == "text_started":
                            if state["reasoning_seen"] and not state["reasoning_done"]:
                                state["reasoning_done"] = True
                                emit(
                                    "model_reasoning",
                                    f"模型分析完成，共接收 {reasoning_characters} 个推理字符",
                                    reasoning_characters=reasoning_characters,
                                    private_reasoning_redacted=True,
                                )
                            emit("skill", "模型已开始组织结构化评审结果", "running")
                        elif kind == "stream_completed" and state["reasoning_seen"] and not state["reasoning_done"]:
                            state["reasoning_done"] = True
                            emit(
                                "model_reasoning",
                                f"模型分析完成，共接收 {reasoning_characters} 个推理字符",
                                reasoning_characters=reasoning_characters,
                                private_reasoning_redacted=True,
                            )

                    return publish_model_event

                try:
                    emit("skill", "正在执行整份简历评审", "running", capability=turn.name)
                    result = bundle.runtime.execute(
                        review_skill.metadata.name, inputs, provider=config["provider"],
                        model=config["model"], session_id=session_id,
                        stream_event_sink=reviewer_stream_sink(),
                    )
                except ValueError as first_error:
                    emit("grounding_retry", "首次结果未通过依据校验，正在进行一次受控重试", "running")
                    failed_usage = self._exception_usage(first_error)
                    retry_inputs = {
                        **inputs,
                        "request": (
                            f"{message}\n\n上一次输出未通过结构或证据校验。"
                            "请只引用上方给出的 block_id，并逐字复制对应文本块中的短原文。"
                        ),
                    }
                    try:
                        result = bundle.runtime.execute(
                            review_skill.metadata.name, retry_inputs, provider=config["provider"],
                            model=config["model"], session_id=session_id,
                            stream_event_sink=reviewer_stream_sink(),
                        )
                        execution_metadata["grounding_retry"] = True
                        emit("grounding_retry", "受控重试已生成新的评审结果")
                    except ValueError as retry_error:
                        failed_usage = self._sum_usage(
                            failed_usage, self._exception_usage(retry_error),
                        )
                        self.repository.record_step(
                            run["id"], skill_name=turn.name,
                            inputs={
                                "artifact_id": artifact.artifact_id,
                                "artifact_version": artifact.version,
                                "section_count": artifact.section_count,
                            },
                            status="degraded", usage=failed_usage, observation={
                                "artifact_resolved": True,
                                "validation": "grounding_failed_after_retry",
                                "errors": [type(first_error).__name__, type(retry_error).__name__],
                            },
                        )
                        execution_metadata.update({
                            "context_events": [
                                "page_state_read", "resume_artifact_identified",
                                "resume_body_resolved", "review_grounding_degraded",
                            ],
                            "artifact_id": artifact.artifact_id,
                            "artifact_version": artifact.version,
                            "artifact_source": artifact.source,
                            "artifact_is_dirty": artifact.is_dirty,
                            "grounding_status": "degraded",
                        })
                        content = (
                            "我已经读取当前简历，但模型连续两次生成的评审依据都无法与正文可靠对应。"
                            "为避免展示未经核验的结论，本次已隐藏这些内容，请重试一次。"
                            if snapshot.get("language") != "en" else
                            "I read the current resume, but two review attempts could not be reliably "
                            "grounded in its text. I withheld the unverified findings; please retry."
                        )
                        emit("harness", "两次依据校验均未通过，已隐藏未经核验的结论", "degraded")
                        return {"content": content, "usage": failed_usage, "degraded": True}
                usage = self._sum_usage(failed_usage, self._usage(result))
                review_output = dict(result.structured_output or {})
                emit("skill", "整份简历评审结果已生成", capability=turn.name)
                removed = int(review_output.get("grounding_removed_count", 0))
                emit(
                    "harness",
                    f"评审依据校验完成{f'，隐藏 {removed} 条无依据评价' if removed else ''}",
                    grounding_removed_count=removed,
                )
                audit_inputs = {
                    "artifact_id": artifact.artifact_id,
                    "artifact_version": artifact.version,
                    "source": artifact.source,
                    "is_dirty": artifact.is_dirty,
                    "section_count": artifact.section_count,
                    "text_characters": len(artifact.text),
                }
                self.repository.record_step(
                    run["id"], skill_name=turn.name, inputs=audit_inputs,
                    status="completed", usage=usage,
                    observation={
                        "artifact_resolved": True,
                        "grounding_status": review_output.get("grounding_status", "grounded"),
                        "grounding_removed_count": review_output.get("grounding_removed_count", 0),
                    },
                )
                execution_metadata.update({
                    "context_events": [
                        "page_state_read", "resume_artifact_identified", "resume_body_resolved",
                        *(["review_grounding_retried"] if execution_metadata.get("grounding_retry") else []),
                    ],
                    "artifact_id": artifact.artifact_id,
                    "artifact_version": artifact.version,
                    "artifact_source": artifact.source,
                    "artifact_is_dirty": artifact.is_dirty,
                    "grounding_status": review_output.get("grounding_status", "grounded"),
                    "grounding_removed_count": review_output.get("grounding_removed_count", 0),
                })
                return {
                    "content": render_skill_result(review_skill, result, inputs),
                    "usage": usage,
                }
            original = str(snapshot.get("selected_text") or "").strip()
            if not original:
                raise ValueError("请先在右侧简历编辑器中选中需要修改的文字")
            requested_mode = str(turn.arguments.get("mode") or "more_professional")
            mode = requested_mode if requested_mode in REWRITE_MODES else "more_professional"
            inputs = {
                "text": original,
                "context": str(snapshot.get("surrounding_context") or "")[:3000],
                "mode": mode,
                "target_language": "en" if snapshot.get("language") == "en" else "zh",
            }
            emit("selection", "已读取当前选中文本")
            emit("skill", "正在生成文本改写建议", "running", capability=turn.name)
            result = bundle.runtime.execute(
                text_skill.metadata.name, inputs, provider=config["provider"], model=config["model"],
                session_id=session_id,
            )
            usage = self._usage(result)
            emit("skill", "文本改写建议已生成", capability=turn.name)
            fact_violations = validate_grounded_text(original, result.content)
            if fact_violations:
                self.repository.record_step(
                    run["id"], skill_name=turn.name, inputs={
                        "target_version": snapshot.get("version", "unsaved"),
                        "original_text_hash": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                    },
                    status="rejected", usage=usage,
                    observation={
                        "validation": "hard_fact_rejected",
                        "violation_count": len(fact_violations),
                    },
                )
                execution_metadata.update({
                    "context_events": ["page_state_read", "selection_read", "mutation_harness_rejected"],
                    "mutation_status": "rejected",
                })
                content = (
                    "本次改写引入了原文中不存在的数字、联系方式或链接，"
                    "硬事实 Harness 已拒绝该建议，右侧简历没有被修改。"
                    if snapshot.get("language") != "en" else
                    "The rewrite introduced a number, contact, or URL absent from the source. "
                    "The hard-fact harness rejected it and the resume was not changed."
                )
                emit("harness", "改写未通过硬事实检查，未生成修改建议", "rejected")
                return {"content": content, "usage": usage, "degraded": True}
            emit("harness", "硬事实检查通过")
            proposal = self.repository.create_proposal(
                run["id"], proposal_type="resume_text_rewrite",
                target_ref=selected_objects[0] if selected_objects else "resume.selection",
                target_version=str(
                    snapshot.get("resume_artifact", {}).get("version")
                    or snapshot.get("version") or "unsaved"
                ),
                payload={
                    "original_text": original,
                    "replacement_text": result.content,
                    "mode": mode,
                    "base_artifact_hash": self._artifact_hash(raw_snapshot),
                    "original_text_hash": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                },
            )
            observation = {"proposal_id": proposal["id"], "proposal_type": proposal["proposal_type"]}
            self.repository.record_step(run["id"], skill_name=turn.name, inputs=inputs,
                                        status="completed", usage=usage, observation=observation)
            execution_metadata["context_events"] = ["page_state_read", "selection_read"]
            emit("proposal", "已生成待确认的改写 Proposal")
            return {"proposal": proposal, "usage": usage}

        try:
            outcome = self.controller.handle(
                DispatchInput(message=message, page=page, selected_objects=selected_objects),
                supervisor=supervise, executor=execute,
                replanner=supervise,
            )
            check_cancelled()
            if outcome.error_code:
                emit("policy", f"执行请求已被策略拒绝：{outcome.error_code}", "rejected")
                emit("failed", f"Policy 拒绝执行：{outcome.error_code}", "failed")
                return self._fail(
                    run, user_message, self._error_message(outcome.error_code), outcome.error_code,
                    runtime_events=runtime_events,
                )
            turn = outcome.turn
            result = outcome.result or {}
            if turn and turn.kind == "clarification":
                emit("policy", "页面权限与回复范围校验通过")
                emit("response", "需要补充的信息已生成")
            proposal = result.get("proposal")
            if proposal:
                proposal_copy = {
                    "resume_generation_request": "已按右侧当前模板、生成方式和目标页数准备好简历生成任务。确认后开始生成。",
                    "interview_preparation_request": "已按右侧职位描述和当前配置准备好面试准备任务。确认后开始生成。",
                    "job_radar_action": "已定位右侧岗位并准备好操作。确认前不会修改收藏、屏蔽或投递记录。",
                }
                content = proposal_copy.get(proposal["proposal_type"], "我已生成一份改写建议。请对比原文和新文，确认后再应用到右侧简历。")
            elif result.get("content"):
                content = str(result["content"])
            elif turn:
                content = MarkdownRenderer.render(AssistantTurnPresenter.present(turn))
            else:
                content = "已完成。"
            content = ensure_formatted_markdown(
                content,
                language="en" if snapshot.get("language") == "en" else "zh",
                title="回答" if snapshot.get("language") != "en" else "Answer",
            )
            usage = self._sum_usage(supervisor_usage, result.get("usage", {}))
            assistant_message = self.repository.add_message(
                session_id, "assistant", content, run_id=run["id"],
                metadata={
                    "mode": outcome.mode.value,
                    "proposal_id": proposal["id"] if proposal else "",
                    "dispatch_path": outcome.dispatch_path,
                    "reason_code": outcome.policy.reason_code if outcome.policy else "",
                    "capability": turn.name if turn and turn.name else "",
                    "total_tokens": usage.get("total_tokens", 0),
                    "runtime_events": runtime_events,
                    "execution_steps": list(outcome.steps),
                    "terminal_reason": outcome.terminal_reason,
                    **execution_metadata,
                },
            )
            finished = self.repository.finish_run(
                run["id"], mode=outcome.mode.value, intent=turn.intent if turn else "",
                dispatch_path=outcome.dispatch_path,
                policy=outcome.policy.model_dump(mode="json") if outcome.policy else {}, usage=usage,
            )
            emit("completed", "处理完成")
            return {"user_message": user_message, "assistant_message": assistant_message,
                    "run": finished, "proposal": proposal}
        except AssistantRunCancelled:
            emit("cancelled", "已按用户请求停止运行", "cancelled")
            finished = self.repository.mark_cancelled(run["id"])
            assistant_message = self.repository.add_message(
                session_id, "assistant", "本次运行已取消。", run_id=run["id"], status="cancelled",
                metadata={"error_code": "cancelled_by_user", "runtime_events": runtime_events},
            )
            return {"user_message": user_message, "assistant_message": assistant_message,
                    "run": finished, "proposal": None}
        except Exception as exc:
            from backend.services.llm_connection_service import diagnose_llm_error
            from src.libs.ai_engine.exceptions import ProviderConfigurationError, ProviderInvocationError

            if isinstance(exc, (ProviderConfigurationError, ProviderInvocationError)):
                error_code, detail = diagnose_llm_error(exc)
            else:
                error_code, detail = type(exc).__name__, str(exc)
            emit("failed", f"处理失败：{detail}", "failed")
            return self._fail(
                run, user_message, detail, error_code, runtime_events=runtime_events,
            )

    def confirm_proposal(self, proposal_id: str) -> dict[str, Any]:
        token = self.repository.issue_confirmation_token(proposal_id)
        return {"confirmation_token": token, "expires_in_seconds": 600}

    def apply_proposal(self, proposal_id: str, confirmation_token: str) -> dict[str, Any]:
        proposal = self.repository.get_proposal(proposal_id)
        if not proposal:
            raise KeyError("Assistant proposal not found")
        if proposal["status"] != "pending":
            raise ValueError(f"Proposal is already {proposal['status']}")
        return self.repository.apply_proposal_with_token(proposal_id, confirmation_token)

    def dismiss_proposal(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.repository.get_proposal(proposal_id)
        if not proposal:
            raise KeyError("Assistant proposal not found")
        return self.repository.set_proposal_status(proposal_id, "dismissed") or proposal

    def undo_proposal(self, proposal_id: str) -> dict[str, Any]:
        return self.repository.undo_proposal(proposal_id)

    def _fail(self, run: dict[str, Any], user_message: dict[str, Any], detail: str,
              error_code: str, runtime_events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        content = ensure_formatted_markdown(
            f"本次处理未完成：{detail}", title="处理失败",
        )
        assistant_message = self.repository.add_message(
            run["session_id"], "assistant", content, run_id=run["id"], status="failed",
            metadata={"error_code": error_code, "runtime_events": runtime_events or []},
        )
        finished = self.repository.finish_run(
            run["id"], mode="chat", intent="", dispatch_path="supervisor", policy={},
            status="failed", error_code=error_code,
        )
        return {"user_message": user_message, "assistant_message": assistant_message,
                "run": finished, "proposal": None}
    @staticmethod
    def _safe_snapshot(
        snapshot: dict[str, Any], artifact_resolver: ResumeArtifactResolver | None = None,
    ) -> dict[str, Any]:
        # Explicit allow-list prevents full DOM, credentials, and unrelated page state entering prompts.
        allowed = {
            "selected_text", "surrounding_context", "language", "version", "summary",
            "job_description", "interview_report", "coding_task", "coding_code",
            "job_preferences", "job_radar_stats", "job_results_meta", "job_results",
            "uploaded_documents", "resume_generation_options",
            "interview_generation_options",
        }
        safe = {key: snapshot[key] for key in allowed if key in snapshot and snapshot[key] is not None}
        if "job_description" in safe:
            safe["job_description"] = str(safe["job_description"])[:12000]
        if "interview_report" in safe:
            safe["interview_report"] = str(safe["interview_report"])[:12000]
        if "coding_code" in safe:
            safe["coding_code"] = str(safe["coding_code"])[:12000]
        if isinstance(safe.get("job_results"), list):
            safe["job_results"] = safe["job_results"][:20]
        resolver = artifact_resolver or ResumeArtifactResolver()
        safe["resume_artifact"] = resolver.metadata(snapshot)
        return safe

    @staticmethod
    def _normalize_context_refs(context_refs: list[str] | None) -> list[str]:
        if context_refs is None:
            return []
        allowed = {
            "resume.current", "resume.selection", "resume.job_description",
            "interview.job_description", "interview.report", "coding.task", "coding.code",
            "radar.preferences", "radar.stats", "radar.results",
        }
        normalized = []
        for ref in context_refs[:20]:
            if ref in allowed:
                normalized.append(ref)
                continue
            if ref.startswith("attachment:"):
                try:
                    UUID(ref.split(":", 1)[1])
                except (ValueError, AttributeError):
                    continue
                normalized.append(ref)
                continue
            if ref.startswith("resume.history:"):
                filename = ref.split("resume.history:", 1)[1]
                if (
                    filename and len(filename) <= 200 and Path(filename).name == filename
                    and Path(filename).suffix.lower() == ".pdf"
                ):
                    normalized.append(ref)
        return list(dict.fromkeys(normalized))

    @staticmethod
    def _load_history_resume_documents(context_refs: list[str]) -> dict[str, dict[str, str]]:
        documents: dict[str, dict[str, str]] = {}
        root = RESUME_OUTPUT_FOLDER.resolve()
        for ref in context_refs:
            if not ref.startswith("resume.history:"):
                continue
            filename = ref.split("resume.history:", 1)[1]
            pdf_path = (root / filename).resolve()
            if pdf_path.parent != root or not pdf_path.is_file():
                continue
            html_path = pdf_path.with_suffix(".html")
            source_path = html_path if html_path.is_file() else pdf_path
            try:
                raw = source_path.read_bytes()
                if len(raw) > MAX_ATTACHMENT_BYTES:
                    continue
                content = extract_text(source_path.name, raw).strip()
            except Exception:
                continue
            if content:
                documents[ref] = {
                    "filename": filename,
                    "content": content[:MAX_STORED_ATTACHMENT_CHARACTERS],
                }
        return documents

    @staticmethod
    def _scope_snapshot(
        snapshot: dict[str, Any], context_refs: list[str], *, explicit: bool = False,
    ) -> dict[str, Any]:
        # No explicit context_refs means a legacy caller; retain the old snapshot contract.
        # An explicit empty list means the user intentionally sent the message without context.
        if not explicit:
            return snapshot
        if not context_refs:
            return {"language": snapshot["language"]} if snapshot.get("language") else {}
        keys_by_ref = {
            "resume.current": {"resume_artifact", "summary", "language", "version"},
            "resume.selection": {"selected_text", "surrounding_context", "language", "version"},
            "resume.job_description": {"job_description", "language"},
            "interview.job_description": {"job_description", "language"},
            "interview.report": {"interview_report", "language"},
            "coding.task": {"coding_task", "language"},
            "coding.code": {"coding_code", "language"},
            "radar.preferences": {"job_preferences", "language"},
            "radar.stats": {"job_radar_stats", "language"},
            "radar.results": {"job_results", "job_results_meta", "language"},
        }
        keys = set().union(*(keys_by_ref[ref] for ref in context_refs if ref in keys_by_ref))
        return {key: value for key, value in snapshot.items() if key in keys}

    @staticmethod
    def _artifact_hash(snapshot: dict[str, Any]) -> str:
        artifact = snapshot.get("resume_artifact")
        if not isinstance(artifact, dict) or not isinstance(artifact.get("content"), str):
            return ""
        return hashlib.sha256(artifact["content"].encode("utf-8")).hexdigest()

    @staticmethod
    def _usage(result: Any) -> dict[str, int]:
        return {"input_tokens": result.usage.input_tokens, "output_tokens": result.usage.output_tokens,
                "total_tokens": result.usage.total_tokens}

    @staticmethod
    def _exception_usage(error: Exception) -> dict[str, int]:
        usage = getattr(error, "skill_usage", None)
        return {
            "input_tokens": int(getattr(usage, "input_tokens", 0)),
            "output_tokens": int(getattr(usage, "output_tokens", 0)),
            "total_tokens": int(getattr(usage, "total_tokens", 0)),
        }

    @staticmethod
    def _sum_usage(first: dict[str, int], second: dict[str, int]) -> dict[str, int]:
        return {key: int(first.get(key, 0)) + int(second.get(key, 0))
                for key in ("input_tokens", "output_tokens", "total_tokens")}

    @staticmethod
    def _error_message(code: str) -> str:
        messages = {
            "page_has_no_assistant": "当前页面未开放助手能力。",
            "empty_message": "请输入要处理的内容。",
            "skill_not_allowed": "当前页面不允许执行这个能力。",
            "action_not_allowed": "当前页面不允许执行这个操作。",
        }
        return messages.get(code, code)
