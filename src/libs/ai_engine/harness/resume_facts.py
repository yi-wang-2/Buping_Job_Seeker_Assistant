"""Fact-preserving resume generation guardrails.

Education is treated as a protected factual section.  A model may receive it
as context, but its generated education HTML is never trusted: the final
section is rendered deterministically from the structured resume source.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any, Iterable, Mapping


PROTECTED_EDUCATION_FIELDS = (
    "education_level",
    "institution",
    "field_of_study",
    "start_date",
    "year_of_completion",
    "final_evaluation_grade",
    "research_direction",
)


@dataclass(frozen=True)
class EducationGuardResult:
    html: str
    protected_fields: tuple[str, ...] = PROTECTED_EDUCATION_FIELDS
    discarded_model_output: bool = False


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return {
        name: getattr(value, name, None)
        for name in (*PROTECTED_EDUCATION_FIELDS, "research_topics", "exam", "additional_info")
    }


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _text(value: Any) -> str:
    return escape(str(value).strip())


def _join_values(value: Any) -> str:
    if not _present(value):
        return ""
    if isinstance(value, Mapping):
        return "、".join(
            f"{_text(key)}（{_text(item)}）" if _present(item) else _text(key)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                items.extend(
                    f"{_text(key)}（{_text(val)}）" if _present(val) else _text(key)
                    for key, val in item.items()
                )
            elif _present(item):
                items.append(_text(item))
        return "、".join(items)
    return _text(value)


def _display_degree(value: Any, *, language: str) -> str:
    if not _present(value):
        return ""
    raw = str(value).strip()
    if language == "en":
        return _text(raw)
    translations = {
        "bachelor": "本科",
        "bachelor's degree": "本科",
        "master": "硕士研究生",
        "master's degree": "硕士研究生",
        "phd": "博士研究生",
        "ph.d.": "博士研究生",
        "doctoral degree": "博士研究生",
    }
    return _text(translations.get(raw.lower(), raw))


def _render_entry(raw: Any, *, language: str) -> str:
    edu = _as_mapping(raw)
    additional = _as_mapping(edu.get("additional_info") or {})

    degree = _display_degree(edu.get("education_level"), language=language)
    major = edu.get("field_of_study")
    title = " · ".join(item for item in (degree, _text(major) if _present(major) else "") if item)
    start = edu.get("start_date")
    end = edu.get("year_of_completion")
    years = " – ".join(_text(item) for item in (start, end) if _present(item))

    research_direction = edu.get("research_direction") or additional.get("research_direction")
    research_topics = edu.get("research_topics") or additional.get("research_topics")
    courses = additional.get("relevant_courses") or additional.get("exam") or edu.get("exam")
    honors = additional.get("honors")
    grade = edu.get("final_evaluation_grade")

    labels = {
        "research": "研究方向" if language != "en" else "Research focus",
        "topics": "研究内容" if language != "en" else "Research topics",
        "courses": "相关课程" if language != "en" else "Relevant coursework",
        "honors": "在校荣誉" if language != "en" else "Honors",
        "gpa": "GPA",
    }
    facts: list[str] = []
    for label, value in (
        (labels["research"], research_direction),
        (labels["topics"], research_topics),
        (labels["courses"], courses),
        (labels["honors"], honors),
    ):
        rendered = _join_values(value)
        if rendered:
            facts.append(f"<li><strong>{label}：</strong>{rendered}</li>")

    grade_html = f'<div class="grade">{labels["gpa"]}: {_text(grade)}</div>' if _present(grade) else ""
    facts_html = f'<ul class="compact-list">{"".join(facts)}</ul>' if facts else ""
    return (
        '<div class="entry">'
        '<div class="entry-header">'
        f'<span class="entry-name">{_text(edu.get("institution")) if _present(edu.get("institution")) else ""}</span>'
        '<span class="entry-location"></span>'
        '</div>'
        '<div class="entry-details">'
        f'<span class="entry-title">{title}</span>'
        f'<span class="entry-year">{years}</span>'
        '</div>'
        f'{grade_html}{facts_html}'
        '</div>'
    )


def protect_education_section(
    education_details: Iterable[Any] | None,
    generated_html: str = "",
    *,
    language: str = "zh",
) -> EducationGuardResult:
    """Return canonical education HTML built only from source facts.

    In particular, when ``research_direction`` is absent, no research focus is
    emitted.  This makes inference from a JD impossible at the output boundary.
    """

    entries = [_render_entry(item, language=language) for item in (education_details or [])]
    if not entries:
        return EducationGuardResult(html="", discarded_model_output=bool(generated_html.strip()))
    heading = "教育背景" if language != "en" else "Education"
    html = f'<section id="education"><h2>{heading}</h2>{"".join(entries)}</section>'
    return EducationGuardResult(
        html=html,
        discarded_model_output=bool(generated_html.strip()),
    )
