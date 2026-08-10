"""Golden-sample scoring and non-destructive hard-fact protection for resumes."""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from bs4 import BeautifulSoup


GOLDEN_RESUME_WRITING_GUIDE = r"""

【黄金样例写作协议 - 必须遵守】
以下规则来自一份经过人工认可的高质量中文简历。学习其叙事结构与信息密度，禁止照抄示例内容。

1. 总体风格
- 使用克制、可信、具体的职业语言；不要堆砌“深度赋能、现象级、极致、颠覆”等空泛宣传词。
- 每条描述只表达一个清晰主题，优先写“职责/行动/方法/结果”，建议 35-95 个汉字。
- 量化数据只能使用输入资料中已经存在的数据。没有数据时写清交付物、技术难点、协作范围或验证标准，严禁编造百分比、人数、排名、销量。
- 姓名、联系方式、学校、专业、学位、公司、职位、地点、日期、项目名称、奖项名称、证书名称必须逐字尊重输入事实。
- 教育经历没有明确研究方向时，不得根据职位描述或工作经历推断研究方向。

2. 工作经历叙事结构
- 每段工作经历输出 3-5 条；每条以 <strong>主题标签：</strong> 开头。
- 根据事实从这些标签中选择：核心职责、项目管理、技术积累、性能优化、问题解决、协作交付、项目成果。
- 示例结构：<li><strong>核心职责：</strong>[职责范围 + 核心对象 + 交付要求]</li>
- 示例结构：<li><strong>项目管理：</strong>[协调对象 + 推进过程 + 验收/交付结果]</li>
- 示例结构：<li><strong>技术积累：</strong>[沉淀的文档、工具、方法或可复用资产]</li>

3. 项目经历叙事结构
- 每个项目输出 2-4 条；每条以 <strong>主题标签：</strong> 开头。
- 根据事实从这些标签中选择：项目背景、项目概述、核心职责、技术实现、技术流程、协作优化、问题解决、项目成果。
- 第一条交代项目背景或目标，中间条目说明本人贡献和技术路径，最后一条在事实允许时说明成果。
- entry-tech 只列输入能够支持的核心技术，不为了匹配职位描述虚构技术栈。

4. 信息密度
- 保留输入中的每段有效经历，但避免同一事实在工作经历、项目经历、荣誉和技能中反复扩写。
- 奖项和证书用一行说明“名称 + 事实依据/价值”，不要编造评选标准、颁发机构或排名。
- 技能按类别组织，熟练程度只有输入明确提供时才能写。
"""


WORK_LABELS = (
    "核心职责", "项目管理", "技术积累", "性能优化", "问题解决", "协作交付", "项目成果",
)
PROJECT_LABELS = (
    "项目背景", "项目概述", "核心职责", "技术实现", "技术流程", "协作优化", "问题解决", "项目成果",
)
GENERIC_HYPE = (
    "深度赋能", "现象级", "极致", "颠覆", "遥遥领先", "显著提升简历通过率", "市场高度认可",
    "全方位赋能", "行业领先", "绝对领先",
)
_NUMBER = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?%?(?![A-Za-z0-9])")
_CONTACT = re.compile(r"(?:https?://\S+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})", re.I)


@dataclass(frozen=True)
class CandidateEvaluation:
    sections: dict[str, str]
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class HardFactResult:
    sections: dict[str, str]
    violations: tuple[str, ...] = ()


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump()
    if value is None:
        return {}
    return {
        name: getattr(value, name, None)
        for name in (
            "name", "surname", "country", "city", "phone_prefix", "phone", "email", "github",
            "linkedin", "wechat", "education_level", "institution", "field_of_study",
            "final_evaluation_grade", "start_date", "year_of_completion", "research_direction",
            "position", "company", "employment_period", "location", "industry",
            "key_responsibilities", "skills_acquired", "description", "link", "language", "proficiency",
        )
    }


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _raw(value: Any) -> str:
    return str(value).strip() if _present(value) else ""


def _flatten(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        result: list[str] = []
        for child in value.values():
            result.extend(_flatten(child))
        return result
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return _flatten(dump())
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for child in value:
            result.extend(_flatten(child))
        return result
    return [_raw(value)] if _present(value) else []


def _source_data(resume: Any) -> dict[str, Any]:
    return _mapping(resume)


def _expected_sections(data: Mapping[str, Any]) -> tuple[str, ...]:
    expected = ["header"]
    for source_key, section_key in (
        ("education_details", "education"), ("experience_details", "work_experience"),
        ("projects", "projects"), ("achievements", "achievements"),
        ("certifications", "certifications"),
    ):
        if data.get(source_key):
            expected.append(section_key)
    if data.get("languages") or data.get("interests") or data.get("experience_details"):
        expected.append("additional_skills")
    return tuple(expected)


def _hard_anchors(data: Mapping[str, Any]) -> list[str]:
    anchors: list[str] = []
    personal = _mapping(data.get("personal_information"))
    anchors.extend(_raw(personal.get(key)) for key in ("name", "surname", "email", "phone") if _present(personal.get(key)))
    for key, fields in (
        ("education_details", ("institution", "field_of_study")),
        ("experience_details", ("company", "position", "employment_period")),
        ("projects", ("name",)), ("achievements", ("name",)), ("certifications", ("name",)),
    ):
        for item in data.get(key) or []:
            source = _mapping(item)
            anchors.extend(_raw(source.get(field)) for field in fields if _present(source.get(field)))
    return [anchor for anchor in anchors if len(anchor) >= 2]


def _new_numeric_or_contact_claims(candidate: str, source: str) -> list[str]:
    candidate_text = BeautifulSoup(candidate or "", "html.parser").get_text(" ", strip=True)
    source_numbers = set(_NUMBER.findall(source))
    source_contacts = set(_CONTACT.findall(source))
    claims = [f"number:{item}" for item in sorted(set(_NUMBER.findall(candidate_text)) - source_numbers)]
    claims.extend(f"contact:{item}" for item in sorted(set(_CONTACT.findall(candidate_text)) - source_contacts))
    return claims


def evaluate_resume_candidate(sections: Mapping[str, str], resume: Any) -> CandidateEvaluation:
    """Score a candidate locally against the golden sample's writing contract."""

    candidate = dict(sections)
    data = _source_data(resume)
    all_html = "\n".join(candidate.values())
    all_text = BeautifulSoup(all_html, "html.parser").get_text(" ", strip=True)
    source_text = "\n".join(_flatten(data))

    expected = _expected_sections(data)
    completeness = 24.0 * sum(bool(candidate.get(key, "").strip()) for key in expected) / max(1, len(expected))

    anchors = _hard_anchors(data)
    coverage = 28.0 * sum(anchor in all_text for anchor in anchors) / max(1, len(anchors))

    soup = BeautifulSoup(all_html, "html.parser")
    work_items = soup.select("#work-experience li")
    project_items = soup.select("#side-projects li")
    themed = 0
    for item, labels in [*((item, WORK_LABELS) for item in work_items), *((item, PROJECT_LABELS) for item in project_items)]:
        strong = item.find("strong")
        label_text = strong.get_text(" ", strip=True) if strong else item.get_text(" ", strip=True).split("：", 1)[0]
        themed += any(label in label_text for label in labels)
    theme_total = len(work_items) + len(project_items)
    narrative = 24.0 * themed / max(1, theme_total)

    bullet_lengths = [len(item.get_text("", strip=True)) for item in soup.select("li")]
    well_sized = sum(16 <= length <= 110 for length in bullet_lengths)
    density = 12.0 * well_sized / max(1, len(bullet_lengths))

    rich_structure = min(6.0, 1.0 * len(soup.select("li > strong")) + 0.5 * len(soup.select(".entry-tech")))
    hype_penalty = 2.0 * sum(all_text.count(phrase) for phrase in GENERIC_HYPE)
    claim_penalty = 5.0 * len(_new_numeric_or_contact_claims(all_html, source_text))
    long_penalty = 1.5 * sum(length > 140 for length in bullet_lengths)
    score = completeness + coverage + narrative + density + rich_structure - hype_penalty - claim_penalty - long_penalty
    breakdown = {
        "completeness": round(completeness, 3), "hard_fact_coverage": round(coverage, 3),
        "golden_narrative": round(narrative, 3), "density": round(density, 3),
        "rich_structure": round(rich_structure, 3), "hype_penalty": round(-hype_penalty, 3),
        "claim_penalty": round(-claim_penalty, 3), "long_bullet_penalty": round(-long_penalty, 3),
    }
    return CandidateEvaluation(candidate, round(score, 3), breakdown)


def select_best_candidate(candidates: Sequence[Mapping[str, str]], resume: Any) -> CandidateEvaluation:
    if not candidates:
        raise ValueError("No resume candidates were generated")
    evaluations = [evaluate_resume_candidate(candidate, resume) for candidate in candidates]
    return max(evaluations, key=lambda item: item.score)


def candidate_count() -> int:
    try:
        configured = int(os.getenv("RESUME_CANDIDATE_COUNT", "3"))
    except ValueError:
        configured = 3
    return max(2, min(3, configured))


def generate_candidates(invoke: Callable[[], str], count: int | None = None) -> list[str]:
    """Generate 2-3 candidates concurrently and retain every successful result."""

    total = candidate_count() if count is None else max(2, min(3, int(count)))
    results: dict[int, str] = {}
    failures: list[Exception] = []
    with ThreadPoolExecutor(max_workers=total) as executor:
        futures = {executor.submit(invoke): index for index in range(total)}
        for future in as_completed(futures):
            index = futures[future]
            try:
                output = future.result()
                if output and output.strip():
                    results[index] = output
            except Exception as exc:  # Preserve provider errors if every candidate fails.
                failures.append(exc)
    if not results:
        if failures:
            raise RuntimeError("All resume candidate generations failed") from failures[0]
        raise RuntimeError("All resume candidate generations returned empty output")
    return [results[index] for index in sorted(results)]


def _replace_text(node: Any, value: Any) -> None:
    if node is None:
        return
    node.clear()
    if _present(value):
        node.append(_raw(value))


def _assign_entries(entries: list[Any], sources: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[int, Any]:
    assigned: dict[int, Any] = {}
    unused = list(entries)
    for index, source in enumerate(sources):
        anchors = [_raw(source.get(field)) for field in fields if _present(source.get(field))]
        match = next(
            (entry for entry in unused if anchors and all(anchor in entry.get_text(" ", strip=True) for anchor in anchors)),
            None,
        )
        if match is None and unused:
            match = unused[0]
        if match is not None:
            assigned[index] = match
            unused.remove(match)
    for entry in unused:
        entry.decompose()
    return assigned


def _filter_claims(container: Any, evidence: str, path: str, violations: list[str]) -> None:
    for index, item in enumerate(list(container.select("li"))):
        claims = _new_numeric_or_contact_claims(str(item), evidence)
        if claims:
            violations.append(f"{path}.{index}: {', '.join(claims)}")
            item.decompose()


def _patch_header(html: str, personal: Any, language: str) -> str:
    if not html.strip():
        return html
    info = _mapping(personal)
    soup = BeautifulSoup(html, "html.parser")
    header = soup.find("header")
    if header is None:
        return html
    name = _raw(info.get("name"))
    surname = _raw(info.get("surname"))
    full_name = f"{name}{' ' if language == 'en' and name and surname else ''}{surname}"
    _replace_text(header.find("h1"), full_name)
    values = {
        "fa-map-marker-alt": ", ".join(filter(None, (_raw(info.get("city")), _raw(info.get("country"))))),
        "fa-phone": " ".join(filter(None, (_raw(info.get("phone_prefix")), _raw(info.get("phone"))))),
        "fa-envelope": _raw(info.get("email")), "fa-linkedin": _raw(info.get("linkedin")),
        "fa-github": _raw(info.get("github")), "fa-weixin": _raw(info.get("wechat")),
    }
    for item in list(header.select(".contact-info p")):
        classes = set(item.get("class") or [])
        key = next((value for value in values if value in classes), None)
        if key is None or not values[key]:
            item.decompose()
            continue
        target = item.find("a") or item.find("span") or item
        if target.name == "a" and values[key].startswith(("http://", "https://")):
            target["href"] = values[key]
            _replace_text(target, "LinkedIn" if key == "fa-linkedin" else "GitHub")
        else:
            target.attrs.pop("href", None)
            _replace_text(target, values[key])
    return str(soup)


def _display_degree(value: Any, language: str) -> str:
    raw = _raw(value)
    if language == "en":
        return raw
    return {
        "bachelor": "本科", "bachelor's degree": "本科", "master": "硕士",
        "master's degree": "硕士", "phd": "博士", "ph.d.": "博士",
    }.get(raw.lower(), raw)


def _patch_education(html: str, education: Iterable[Any], language: str, violations: list[str]) -> str:
    if not html.strip():
        return html
    sources = [_mapping(item) for item in education]
    soup = BeautifulSoup(html, "html.parser")
    entries = list(soup.select("#education .entry")) or list(soup.select(".entry"))
    assigned = _assign_entries(entries, sources, ("institution", "field_of_study"))
    for index, source in enumerate(sources):
        entry = assigned.get(index)
        if entry is None:
            continue
        entry["data-source-id"] = f"education-{index}"
        _replace_text(entry.select_one(".entry-name"), source.get("institution"))
        degree = _display_degree(source.get("education_level"), language)
        major = _raw(source.get("field_of_study"))
        _replace_text(entry.select_one(".entry-title"), " · ".join(filter(None, (degree, major))))
        years = " – ".join(filter(None, (_raw(source.get("start_date")), _raw(source.get("year_of_completion")))))
        _replace_text(entry.select_one(".entry-year"), years)
        grade = entry.select_one(".grade")
        if grade is not None:
            if _present(source.get("final_evaluation_grade")):
                _replace_text(grade, f"GPA: {_raw(source.get('final_evaluation_grade'))}")
            else:
                grade.decompose()
        research = _raw(source.get("research_direction"))
        for item in list(entry.select("li")):
            if "研究方向" in item.get_text(" ", strip=True) and not research:
                violations.append(f"education_details.{index}.research_direction: invented")
                item.decompose()
        _filter_claims(entry, "\n".join(_flatten(source)), f"education_details.{index}", violations)
    return str(soup)


def _patch_work(html: str, experiences: Iterable[Any], violations: list[str]) -> str:
    if not html.strip():
        return html
    sources = [_mapping(item) for item in experiences]
    soup = BeautifulSoup(html, "html.parser")
    entries = list(soup.select("#work-experience .entry")) or list(soup.select(".entry"))
    assigned = _assign_entries(entries, sources, ("company", "position"))
    for index, source in enumerate(sources):
        entry = assigned.get(index)
        if entry is None:
            continue
        entry["data-source-id"] = f"experience-{index}"
        for selector, field in (
            (".entry-name", "company"), (".entry-location", "location"),
            (".entry-title", "position"), (".entry-year", "employment_period"),
        ):
            _replace_text(entry.select_one(selector), source.get(field))
        _filter_claims(entry, "\n".join(_flatten(source)), f"experience_details.{index}", violations)
    return str(soup)


def _patch_projects(html: str, projects: Iterable[Any], violations: list[str]) -> str:
    if not html.strip():
        return html
    sources = [_mapping(item) for item in projects]
    soup = BeautifulSoup(html, "html.parser")
    entries = list(soup.select("#side-projects .entry")) or list(soup.select(".entry"))
    assigned = _assign_entries(entries, sources, ("name",))
    for index, source in enumerate(sources):
        entry = assigned.get(index)
        if entry is None:
            continue
        entry["data-source-id"] = f"project-{index}"
        container = entry.select_one(".entry-name")
        anchor = container.find("a") if container else None
        if anchor is not None:
            _replace_text(anchor, source.get("name"))
            if _present(source.get("link")):
                anchor["href"] = _raw(source.get("link"))
            else:
                anchor.attrs.pop("href", None)
        elif container is not None:
            _replace_text(container, source.get("name"))
        _filter_claims(entry, "\n".join(_flatten(source)), f"projects.{index}", violations)
    return str(soup)


def _patch_named_items(html: str, sources_raw: Iterable[Any], section_name: str, violations: list[str], extra_names: Iterable[str] = ()) -> str:
    if not html.strip():
        return html
    sources = [_mapping(item) for item in sources_raw]
    allowed = [_raw(source.get("name")) for source in sources if _present(source.get("name"))]
    allowed.extend(_raw(name) for name in extra_names if _present(name))
    if not allowed:
        return ""
    evidence = "\n".join([*_flatten(sources), *allowed])
    soup = BeautifulSoup(html, "html.parser")
    for index, item in enumerate(list(soup.select("li"))):
        strong = item.find("strong")
        name = strong.get_text(" ", strip=True).strip("：: ") if strong else item.get_text(" ", strip=True).split("：", 1)[0]
        if allowed and not any(candidate in name or name in candidate for candidate in allowed):
            violations.append(f"{section_name}.{index}.name: {name}")
            item.decompose()
            continue
        claims = _new_numeric_or_contact_claims(str(item), evidence)
        if claims:
            violations.append(f"{section_name}.{index}: {', '.join(claims)}")
            item.decompose()
    return str(soup)


def _patch_additional(html: str, resume: Any, violations: list[str]) -> str:
    if not html.strip():
        return html
    data = _source_data(resume)
    soup = BeautifulSoup(html, "html.parser")
    _filter_claims(soup, "\n".join(_flatten(data)), "additional_skills", violations)
    languages = []
    for raw_language in data.get("languages") or []:
        language = _mapping(raw_language)
        value = "（".join(filter(None, (_raw(language.get("language")), _raw(language.get("proficiency")))))
        if value and _present(language.get("proficiency")):
            value += "）"
        if value:
            languages.append(value)
    interests = [_raw(item) for item in data.get("interests") or [] if _present(item)]
    for item in soup.select("#languages-other li, #skills-languages li"):
        label = item.find("strong")
        label_text = label.get_text(" ", strip=True).lower() if label else ""
        replacement = None
        if "语言" in label_text or "language" in label_text or "英语" in label_text or "普通话" in label_text:
            replacement = "、".join(languages)
        elif "兴趣" in label_text or "interest" in label_text:
            replacement = "、".join(interests)
        if replacement is not None:
            preserved_label = str(label) if label else ""
            item.clear()
            if preserved_label:
                item.append(BeautifulSoup(preserved_label, "html.parser").find("strong"))
            item.append(replacement)
    return str(soup)


def protect_hard_facts_in_place(
    sections: Mapping[str, str], resume: Any, *, language: str = "zh"
) -> HardFactResult:
    """Patch only immutable facts; preserve the selected candidate's HTML structure."""

    result = dict(sections)
    data = _source_data(resume)
    violations: list[str] = []
    result["header"] = _patch_header(result.get("header", ""), data.get("personal_information"), language)
    result["education"] = _patch_education(
        result.get("education", ""), data.get("education_details") or [], language, violations
    )
    result["work_experience"] = _patch_work(
        result.get("work_experience", ""), data.get("experience_details") or [], violations
    )
    result["projects"] = _patch_projects(result.get("projects", ""), data.get("projects") or [], violations)
    result["achievements"] = _patch_named_items(
        result.get("achievements", ""), data.get("achievements") or [], "achievements", violations
    )
    language_names = [
        value for language_item in data.get("languages") or [] for value in _flatten(language_item)
    ]
    result["certifications"] = _patch_named_items(
        result.get("certifications", ""), data.get("certifications") or [], "certifications", violations,
        extra_names=language_names,
    )
    result["additional_skills"] = _patch_additional(result.get("additional_skills", ""), resume, violations)
    return HardFactResult(result, tuple(violations))
