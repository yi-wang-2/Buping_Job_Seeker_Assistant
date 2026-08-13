from __future__ import annotations

from typing import Any

from ....context import ContextItem, ContextKind, TokenBudget
from ....models import LLMResponse, Message
from ...base import SkillMetadata, SkillResult
from ...schemas import ResumeWriterInput
from .prompts import build_resume_generation_prompt


class ResumeWriterSkill:
    metadata = SkillMetadata(
        "resume_writer", "3.0.0", "Build the resume prompt from structured facts and generate marked HTML sections.",
        TokenBudget(32000, 5000, 2200, 1200), memory_read=("resume_style",),
        memory_write=("resume_versions",), tags=("resume", "writing"), cacheable=False,
        context_weights={"system": .10, "task": .80, "long_term": .10},
        input_schema=ResumeWriterInput,
    )
    SYSTEM = (
        "你是专业简历作者。只能依据结构化简历事实优化结构、叙事和措辞；"
        "可以适配 JD，但不得新增输入无法支持的公司、项目、数字、技能、研究方向或经历。"
        "严格遵守用户任务中的模块标记与 HTML 输出协议。"
    )

    def validate_input(self, inputs: dict[str, Any]) -> None:
        if not isinstance(inputs.get("resume"), dict) or not inputs["resume"]:
            raise ValueError("Missing required inputs: resume")

    def context_items(self, inputs: dict[str, Any]) -> list[ContextItem]:
        return [
            ContextItem("resume-writer-system", ContextKind.SYSTEM, self.SYSTEM, "skill", protected=True, priority=100, relevance=1),
            ContextItem("resume-writer-request", ContextKind.TASK, build_resume_generation_prompt(inputs), "resume_workflow", protected=True, priority=100, relevance=1),
        ]

    def build_messages(self, inputs: dict[str, Any], context: tuple[ContextItem, ...]) -> tuple[Message, ...]:
        by_id = {item.id: item.content for item in context}
        return Message("system", by_id["resume-writer-system"]), Message("user", by_id["resume-writer-request"])

    def parse_output(self, response: LLMResponse) -> SkillResult:
        return SkillResult(content=response.content.strip(), usage=response.usage)
