from __future__ import annotations

import json
from typing import Any

from ...context import ContextItem, ContextKind, TokenBudget
from ...models import LLMResponse, Message
from ..base import SkillMetadata, SkillResult


class _PromptSkill:
    metadata: SkillMetadata
    required_inputs: tuple[str, ...] = ()
    system_prompt = ""

    def validate_input(self, inputs: dict[str, Any]) -> None:
        missing = [name for name in self.required_inputs if not str(inputs.get(name, "")).strip()]
        if missing:
            raise ValueError(f"Missing required inputs: {', '.join(missing)}")

    def context_items(self, inputs: dict[str, Any]) -> list[ContextItem]:
        items = [ContextItem(f"{self.metadata.name}-system", ContextKind.SYSTEM, self.system_prompt, "skill", priority=100, relevance=1, protected=True)]
        for index, (name, value) in enumerate(inputs.items()):
            if value in (None, "", [], {}):
                continue
            kind = ContextKind.HISTORY if name in {"history", "messages"} else ContextKind.TASK
            content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            items.append(ContextItem(f"{self.metadata.name}-{name}-{index}", kind, f"{name}:\n{content}", "user", priority=90, relevance=1, protected=name in self.required_inputs))
        return items

    def build_messages(self, inputs: dict[str, Any], context: tuple[ContextItem, ...]) -> tuple[Message, ...]:
        system = next(item.content for item in context if item.kind == ContextKind.SYSTEM)
        body = "\n\n".join(item.content for item in context if item.kind != ContextKind.SYSTEM)
        return Message("system", system), Message("user", body)

    def parse_output(self, response: LLMResponse) -> SkillResult:
        return SkillResult(content=response.content.strip(), usage=response.usage)


class InterviewCoachSkill(_PromptSkill):
    metadata = SkillMetadata(
        "interview_coach", "1.1.0", "Generate evidence-grounded interview preparation.",
        TokenBudget(32000, 8000, 1800, 1000), memory_read=("interview_weaknesses",),
        tags=("interview", "coaching"),
        context_weights={"system": .15, "request": .05, "task": .70, "working": .05, "long_term": .03, "history": .02},
    )
    required_inputs = ("resume", "job_description")
    system_prompt = "你是资深面试教练。仅依据简历和 JD 给出准备计划、可能问题、回答要点和反问建议；不得虚构候选人经历。"

    def parse_output(self, response: LLMResponse) -> SkillResult:
        return SkillResult(
            content=response.content.strip(),
            structured_output={"finish_reason": response.finish_reason},
            usage=response.usage,
        )

    def context_items(self, inputs: dict[str, Any]) -> list[ContextItem]:
        prepared_prompt = str(inputs.get("prepared_prompt", "")).strip()
        if not prepared_prompt:
            return super().context_items(inputs)
        return [
            ContextItem("interview-coach-system", ContextKind.SYSTEM, self.system_prompt, "skill", priority=100, relevance=1, protected=True),
            ContextItem("interview-coach-report", ContextKind.TASK, prepared_prompt, "user", priority=100, relevance=1, protected=True),
        ]

    def build_messages(self, inputs: dict[str, Any], context: tuple[ContextItem, ...]) -> tuple[Message, ...]:
        by_id = {item.id: item.content for item in context}
        if "interview-coach-report" in by_id:
            return Message("system", by_id["interview-coach-system"]), Message("user", by_id["interview-coach-report"])
        return super().build_messages(inputs, context)


class MockInterviewerSkill(_PromptSkill):
    metadata = SkillMetadata(
        "mock_interviewer", "1.0.0", "Run one stateful mock-interview turn.",
        TokenBudget(16000, 1200, 1600, 800), memory_read=("interview_weaknesses",),
        memory_write=("interview_weaknesses",), tags=("interview", "dialogue"), cacheable=False,
    )
    required_inputs = ("resume", "job_description")
    system_prompt = "你是专业面试官。结合 JD、简历和最近对话，一次只提出一个清晰问题；追问必须基于候选人刚才的回答，不得虚构事实。"


class ResumeWriterSkill(_PromptSkill):
    metadata = SkillMetadata(
        "resume_writer", "1.0.0", "Tailor a resume to a job without inventing facts.",
        TokenBudget(32000, 5000, 2200, 1200), memory_read=("resume_style",),
        memory_write=("resume_versions",), tags=("resume", "writing"),
    )
    required_inputs = ("resume",)
    system_prompt = "你是专业简历作者。优化结构和措辞并适配 JD，但不得新增原始简历无法支持的公司、项目、数字、技能或经历。保持输入语言并输出结构化简历正文。"


class SkillMatcherSkill(_PromptSkill):
    metadata = SkillMetadata(
        "skill_matcher", "1.0.0", "Compare resume evidence with JD requirements.",
        TokenBudget(18000, 2500, 1600, 800), memory_read=("job_preferences",),
        tags=("job", "matching"),
    )
    required_inputs = ("resume", "job_description")
    system_prompt = "你是技能匹配分析器。逐项用简历证据对照 JD，输出匹配项、缺口、证据和改进建议；没有证据的技能必须标记为缺口，不能推断为已掌握。"


class CareerAdvisorSkill(_PromptSkill):
    metadata = SkillMetadata(
        "career_advisor", "1.0.0", "Create an actionable career plan.",
        TokenBudget(24000, 3500, 1800, 1000),
        memory_read=("job_preferences", "career_goals", "interview_weaknesses"),
        memory_write=("career_goals",), tags=("career", "planning"),
    )
    required_inputs = ("resume",)
    system_prompt = "你是职业顾问。基于用户履历、明确偏好和历史反馈给出可执行建议，区分事实、推断与建议，并标注优先级和下一步。"

