from __future__ import annotations

import re
from typing import Any

from ..skills.base import SkillResult
from .markdown import MarkdownRenderer
from .models import HeadingBlock, ParagraphBlock, ResponseDocument


def build_skill_presentation(
    skill: Any, result: SkillResult, inputs: dict[str, Any],
) -> ResponseDocument | None:
    if result.presentation is not None:
        return result.presentation
    presenter = getattr(skill, "presenter", None)
    if presenter is None:
        return None
    return presenter.present(result.structured_output, inputs=inputs)


def render_skill_result(skill: Any, result: SkillResult, inputs: dict[str, Any]) -> str:
    document = build_skill_presentation(skill, result, inputs)
    if document is not None:
        return MarkdownRenderer.render(document)
    language = str(inputs.get("language") or inputs.get("target_language") or "zh")
    return ensure_formatted_markdown(result.content, language=language)


def ensure_formatted_markdown(
    content: str, *, language: str = "zh", title: str | None = None,
) -> str:
    """Keep every assistant-visible result inside a minimal Markdown document."""
    text = str(content or "").strip()
    if not text:
        text = "已完成。" if language != "en" else "Completed."
    if re.match(r"^\s{0,3}#{1,6}\s+", text):
        return text
    resolved_title = title or ("处理结果" if language != "en" else "Result")
    return MarkdownRenderer.render(ResponseDocument((
        HeadingBlock(resolved_title),
        ParagraphBlock(text),
    )))
