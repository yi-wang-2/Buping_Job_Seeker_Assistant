"""Build a generation source from the experiences visible in an edited resume.

The saved HTML is the user's selection: hidden library entries are deliberately
excluded. Existing entries retain their canonical YAML facts; newly added
entries are promoted from the edited document into the generation source.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

import yaml
from bs4 import BeautifulSoup, Tag


_SECTIONS = {
    "education_details": ("education",),
    "experience_details": ("work-experience",),
    "projects": ("side-projects", "projects"),
}
_SOURCE_PREFIX = {
    "education_details": "education",
    "experience_details": "experience",
    "projects": "project",
}
_IDENTITY_FIELD = {
    "education_details": "institution",
    "experience_details": "company",
    "projects": "name",
}


def _text(entry: Tag, selector: str) -> str:
    node = entry.select_one(selector)
    return node.get_text(" ", strip=True) if node else ""


def _new_entry(entry: Tag, category: str) -> dict[str, Any] | None:
    title = _text(entry, ".entry-name")
    if not title or title in {"学校名称", "公司或组织名称", "项目名称"}:
        return None
    detail = _text(entry, ".entry-title")
    if detail in {"学历 · 专业", "项目经历", "项目角色"}:
        detail = ""
    period = _text(entry, ".entry-year")
    bullets = [node.get_text(" ", strip=True) for node in entry.select("li")]
    bullets = [item for item in bullets if item]
    if category == "education_details":
        degree, _, major = detail.partition(" · ")
        years = re.findall(r"\b(?:19|20)\d{2}\b", period)
        result: dict[str, Any] = {
            "institution": title,
            "education_level": degree,
            "field_of_study": major,
            "location": _text(entry, ".entry-location"),
        }
        if years:
            result["start_date"] = years[0]
        if len(years) > 1:
            result["year_of_completion"] = int(years[-1])
        highlight = _text(entry, ".education-highlight")
        if highlight:
            result["additional_info"] = {"relevant_courses": highlight.split("：", 1)[-1].strip()}
        elif bullets:
            result["additional_info"] = {"relevant_courses": "；".join(bullets)}
        return result
    if category == "experience_details":
        if detail in {"工作岗位", "实习岗位"}:
            return None
        return {
            "company": title,
            "position": detail,
            "location": _text(entry, ".entry-location"),
            "employment_period": period,
            "key_responsibilities": [{"responsibility": item} for item in bullets],
        }
    return {
        "name": title,
        "project_level": str(entry.select_one(".entry-name").get("data-project-level") or "")
        if entry.select_one(".entry-name") else "",
        "project_role": detail,
        "time_period": period,
        "description": "；".join(bullets),
    }


def _matches_source(entry: Tag, source: Any, category: str) -> bool:
    if not isinstance(source, dict):
        return False
    title = _text(entry, ".entry-name")
    if title != str(source.get(_IDENTITY_FIELD[category]) or "").strip():
        return False
    if category == "experience_details":
        position = _text(entry, ".entry-title")
        return not position or position == str(source.get("position") or "").strip()
    return True


def select_visible_experiences(source_yaml: str, current_html: str) -> str:
    """Return YAML containing only active resume entries, in displayed order."""
    if not current_html.strip():
        return source_yaml
    data = yaml.safe_load(source_yaml)
    if not isinstance(data, dict):
        raise ValueError("Resume YAML must contain an object")
    soup = BeautifulSoup(current_html, "html.parser")
    if soup.find("header") is None:
        raise ValueError("Current resume HTML has no header; cannot select experiences safely")
    # The lightweight YAML preview uses unlabelled .preview-item blocks and is
    # not an editable experience selection. Before the first generated resume,
    # the original YAML remains the source of truth.
    if soup.find("main") is None and not soup.select(
        "section#education, section#work-experience, section#side-projects, "
        "section#projects, #buping-experience-library-store"
    ):
        return source_yaml
    selected = deepcopy(data)
    for category, section_ids in _SECTIONS.items():
        sources = data.get(category) or []
        if not isinstance(sources, list):
            sources = []
        active: list[dict[str, Any]] = []
        used: set[int] = set()
        for section_id in section_ids:
            section = soup.find("section", id=section_id)
            if section is None or section.has_attr("hidden"):
                continue
            entries = section.select(":scope > .entry, :scope > .resume-card")
            for entry in entries:
                if entry.has_attr("hidden"):
                    continue
                source_id = str(entry.get("data-source-id") or "")
                match = re.fullmatch(rf"{_SOURCE_PREFIX[category]}-(\d+)", source_id)
                index = int(match.group(1)) if match else -1
                if not (0 <= index < len(sources) and index not in used
                        and _matches_source(entry, sources[index], category)):
                    matches = [
                        i for i, source in enumerate(sources)
                        if i not in used and _matches_source(entry, source, category)
                    ]
                    index = matches[0] if len(matches) == 1 else -1
                if index >= 0:
                    active.append(deepcopy(sources[index]))
                    used.add(index)
                else:
                    added = _new_entry(entry, category)
                    if added:
                        active.append(added)
        selected[category] = active
    return yaml.safe_dump(selected, allow_unicode=True, sort_keys=False)


def carry_experience_library(current_html: str, generated_html: str) -> str:
    """Keep the withdrawn-entry library when replacing the visible resume."""
    if not current_html.strip():
        return generated_html
    source = BeautifulSoup(current_html, "html.parser")
    store = source.find(id="buping-experience-library-store")
    if store is None or not store.select("[data-buping-library-item]"):
        return generated_html
    result = BeautifulSoup(generated_html, "html.parser")
    if result.body is None:
        return generated_html
    existing = result.find(id="buping-experience-library-store")
    if existing:
        existing.decompose()
    labels = {"education": "教育背景", "work-experience": "工作经历",
              "side-projects": "项目经历", "projects": "项目经历"}
    for item in store.select("[data-buping-library-item]"):
        section_id = str(item.get("data-buping-library-section-id") or "")
        if section_id in labels and result.find("section", id=section_id) is None:
            section = result.new_tag("section", id=section_id)
            section["hidden"] = ""
            section["data-buping-library-empty-section"] = "true"
            heading = result.new_tag("h2")
            heading.string = labels[section_id]
            section.append(heading)
            result.body.append(section)
    result.body.append(store.extract())
    return str(result)
