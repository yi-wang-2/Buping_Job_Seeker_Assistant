from __future__ import annotations

import re
from typing import Any

from ....context import ContextItem, ContextKind, TokenBudget
from ....models import LLMResponse, Message
from ...base import SkillMetadata, SkillResult


class TextRewriterSkill:
    metadata = SkillMetadata(
        name="text_rewriter",
        version="1.0.0",
        description="Rewrite resume text with a selected editing mode.",
        token_budget=TokenBudget(model_context_limit=12000, reserved_output=2000, reserved_system=1200, safety_margin=500),
        memory_read=("resume_style",),
        tags=("resume", "writing"),
    )

    def __init__(self, prompts: dict[str, dict[str, str]]) -> None:
        self.prompts = prompts

    def validate_input(self, inputs: dict[str, Any]) -> None:
        if not str(inputs.get("text", "")).strip():
            raise ValueError("Text to rewrite cannot be empty")
        language = "en" if inputs.get("target_language") == "en" else "zh"
        if inputs.get("mode") not in self.prompts.get(language, {}):
            raise ValueError(f"Unsupported rewrite mode: {inputs.get('mode')}")

    def context_items(self, inputs: dict[str, Any]) -> list[ContextItem]:
        language = "en" if inputs.get("target_language") == "en" else "zh"
        items = [
            ContextItem("rewrite-system", ContextKind.SYSTEM, self.prompts[language][inputs["mode"]], "skill", protected=True, priority=100, relevance=1),
            ContextItem("rewrite-text", ContextKind.REQUEST, str(inputs["text"]), "user", protected=True, priority=100, relevance=1),
        ]
        if str(inputs.get("context", "")).strip():
            items.append(ContextItem("rewrite-context", ContextKind.WORKING, str(inputs["context"]), "user", priority=70, relevance=0.8))
        return items

    def build_messages(self, inputs: dict[str, Any], context: tuple[ContextItem, ...]) -> tuple[Message, ...]:
        by_id = {item.id: item.content for item in context}
        text = by_id.get("rewrite-text", str(inputs["text"]))
        surrounding = by_id.get("rewrite-context", "")
        user = f"【需要改写的文本】\n{text}"
        if surrounding:
            user = f"【上下文（仅供参考，无需修改）】\n{surrounding}\n\n{user}"
        return (Message("system", by_id["rewrite-system"]), Message("user", user))

    def parse_output(self, response: LLMResponse) -> SkillResult:
        content = re.sub(r"^```[a-zA-Z]*\s*|\s*```\s*$", "", response.content.strip())
        return SkillResult(content=content, usage=response.usage)

