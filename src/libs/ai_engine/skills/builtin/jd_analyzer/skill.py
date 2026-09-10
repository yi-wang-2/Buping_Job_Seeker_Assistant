from __future__ import annotations

import json
from typing import Any

from ....context import ContextItem, ContextKind, TokenBudget
from ....models import LLMResponse, Message
from ...base import SkillMetadata, SkillResult, ToolCall
from ...schemas import JDAnalysis, JDAnalyzerInput


class JDAnalyzerSkill:
    metadata = SkillMetadata(
        name="jd_analyzer",
        version="1.0.0",
        description="Extract structured requirements from a job description.",
        token_budget=TokenBudget(model_context_limit=16000, reserved_output=2000, reserved_system=1200, safety_margin=500),
        memory_read=("job_preferences",),
        memory_write=("job_descriptions",),
        tags=("job", "analysis"),
        input_schema=JDAnalyzerInput,
        output_schema=JDAnalysis,
        tools=("archive_job_description",),
    )

    SYSTEM = """你是职位描述分析器。仅根据输入 JD 提取信息，不得补充未出现的要求。严格输出 JSON，字段为 role、company、responsibilities、required_skills、preferred_skills、experience_years、education、location、salary、keywords。未知标量使用 null，未知列表使用空列表。"""

    def validate_input(self, inputs: dict[str, Any]) -> None:
        if not str(inputs.get("job_description", "")).strip():
            raise ValueError("Job description cannot be empty")

    def context_items(self, inputs: dict[str, Any]) -> list[ContextItem]:
        return [
            ContextItem("jd-system", ContextKind.SYSTEM, self.SYSTEM, "skill", protected=True, priority=100, relevance=1),
            ContextItem("jd-text", ContextKind.TASK, str(inputs["job_description"]), "user", protected=True, priority=100, relevance=1),
        ]

    def build_messages(self, inputs: dict[str, Any], context: tuple[ContextItem, ...]) -> tuple[Message, ...]:
        by_id = {item.id: item.content for item in context}
        return (Message("system", by_id["jd-system"]), Message("user", by_id["jd-text"]))

    def parse_output(self, response: LLMResponse) -> SkillResult:
        raw = response.content.strip().removeprefix("```json").removesuffix("```").strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("JD analyzer output must be a JSON object")
        return SkillResult(content=raw, structured_output=parsed, usage=response.usage)

    def build_tool_calls(self, result: SkillResult, inputs: dict[str, Any]) -> tuple[ToolCall, ...]:
        analysis = dict(result.structured_output or {})
        return (ToolCall("archive_job_description", {
            "raw_text": inputs["job_description"], "normalized": analysis,
            "company": str(analysis.get("company") or ""), "role": str(analysis.get("role") or ""),
            "source_url": str(inputs.get("source_url") or ""),
        }),)

