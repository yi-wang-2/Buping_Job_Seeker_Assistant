"""Fact policies and fail-closed guardrails for generated resumes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from html import escape
from typing import Any, Iterable, Mapping

from bs4 import BeautifulSoup


class FactPolicy(str, Enum):
    """How AI is allowed to interact with a resume field."""

    LOCKED = "locked"
    GROUNDED_REWRITE = "grounded_rewrite"
    GENERATIVE = "generative"


FACT_POLICY: dict[str, FactPolicy] = {
    "personal_information.*": FactPolicy.LOCKED,
    "education_details.*.*": FactPolicy.LOCKED,
    "experience_details.*.position": FactPolicy.LOCKED,
    "experience_details.*.company": FactPolicy.LOCKED,
    "experience_details.*.employment_period": FactPolicy.LOCKED,
    "experience_details.*.location": FactPolicy.LOCKED,
    "experience_details.*.industry": FactPolicy.LOCKED,
    "experience_details.*.skills_acquired": FactPolicy.GROUNDED_REWRITE,
    "experience_details.*.key_responsibilities": FactPolicy.GROUNDED_REWRITE,
    "projects.*.name": FactPolicy.LOCKED,
    "projects.*.link": FactPolicy.LOCKED,
    "projects.*.description": FactPolicy.GROUNDED_REWRITE,
    "achievements.*.name": FactPolicy.LOCKED,
    "achievements.*.description": FactPolicy.GROUNDED_REWRITE,
    "academic_achievements.*.*": FactPolicy.LOCKED,
    "certifications.*.name": FactPolicy.LOCKED,
    "certifications.*.description": FactPolicy.GROUNDED_REWRITE,
    "languages.*.*": FactPolicy.LOCKED,
    "interests.*": FactPolicy.LOCKED,
    "professional_summary": FactPolicy.GENERATIVE,
}

PROTECTED_EDUCATION_FIELDS = (
    "education_level",
    "institution",
    "field_of_study",
    "start_date",
    "year_of_completion",
    "final_evaluation_grade",
    "research_direction",
)

_NUMERIC_CLAIM = re.compile(r"\d+(?:\.\d+)?%?")
_URL_OR_EMAIL = re.compile(r"(?:https?://\S+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})", re.I)


@dataclass(frozen=True)
class GuardViolation:
    path: str
    reason: str
    generated: str = ""


@dataclass(frozen=True)
class EducationGuardResult:
    html: str
    protected_fields: tuple[str, ...] = PROTECTED_EDUCATION_FIELDS
    discarded_model_output: bool = False


@dataclass
class ResumeGuardResult:
    sections: dict[str, str]
    violations: list[GuardViolation] = field(default_factory=list)

    @property
    def blocked_count(self) -> int:
        return len(self.violations)


def policy_for(path: str) -> FactPolicy:
    """Resolve a concrete dotted path against the policy registry."""

    parts = path.split(".")
    for pattern, policy in FACT_POLICY.items():
        expected = pattern.split(".")
        if len(parts) == len(expected) and all(a == b or b == "*" for a, b in zip(parts, expected)):
            return policy
    raise KeyError(f"No resume fact policy registered for {path}")


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    if value is None:
        return {}
    names = (
        *PROTECTED_EDUCATION_FIELDS, "research_topics", "exam", "additional_info",
        "full_name", "name", "surname", "country", "city", "address", "phone_prefix",
        "phone", "email", "github", "linkedin", "wechat", "position", "company",
        "employment_period", "location", "industry", "key_responsibilities",
        "skills_acquired", "description", "link", "proficiency", "language",
    )
    return {name: getattr(value, name, None) for name in names}


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _text(value: Any) -> str:
    return escape(str(value).strip())


def _raw_text(value: Any) -> str:
    return str(value).strip() if _present(value) else ""


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
        "bachelor": "本科", "bachelor's degree": "本科",
        "master": "硕士研究生", "master's degree": "硕士研究生",
        "phd": "博士研究生", "ph.d.": "博士研究生",
        "doctoral degree": "博士研究生",
    }
    return _text(translations.get(raw.lower(), raw))


def _flatten_facts(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        result: list[str] = []
        for item in value.values():
            result.extend(_flatten_facts(item))
        return result
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _flatten_facts(model_dump())
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            result.extend(_flatten_facts(item))
        return result
    return [_raw_text(value)] if _present(value) else []


def validate_grounded_text(source: str, candidate: str) -> list[str]:
    """Protect only verifiable numeric/contact facts in generated prose."""

    source = source.strip()
    candidate = BeautifulSoup(candidate or "", "html.parser").get_text(" ", strip=True)
    if not candidate:
        return ["empty rewrite"]

    reasons: list[str] = []
    source_numbers = set(_NUMERIC_CLAIM.findall(source))
    new_numbers = set(_NUMERIC_CLAIM.findall(candidate)) - source_numbers
    if new_numbers:
        reasons.append(f"new numeric claims: {sorted(new_numbers)}")

    source_contacts = set(_URL_OR_EMAIL.findall(source))
    new_contacts = set(_URL_OR_EMAIL.findall(candidate)) - source_contacts
    if new_contacts:
        reasons.append("new contact or URL")

    return reasons


def _extract_safe_entry_bullets(
    generated_html: str,
    anchors: Iterable[str],
    source_bullets: list[str],
    supporting_evidence: Iterable[str] = (),
    *,
    path: str,
) -> tuple[list[str], list[GuardViolation]]:
    if not generated_html:
        return source_bullets, []
    anchors = [anchor for anchor in anchors if anchor]
    soup = BeautifulSoup(generated_html, "html.parser")
    for entry in soup.select(".entry"):
        entry_text = entry.get_text(" ", strip=True)
        if anchors and all(anchor in entry_text for anchor in anchors):
            candidates = [item.get_text(" ", strip=True) for item in entry.select("li")]
            if not candidates:
                break
            evidence = "\n".join([*source_bullets, *(item for item in supporting_evidence if item)])
            safe: list[str] = []
            violations: list[GuardViolation] = []
            for candidate in candidates:
                reasons = validate_grounded_text(evidence, candidate)
                if reasons:
                    violations.append(GuardViolation(path, "; ".join(reasons), candidate))
                else:
                    safe.append(candidate)
            return (safe if safe else source_bullets), violations
    return source_bullets, []


def _render_header(personal: Any, *, language: str) -> str:
    info = _as_mapping(personal)
    full_name = _raw_text(info.get("full_name"))
    if not full_name:
        name = _raw_text(info.get("name"))
        surname = _raw_text(info.get("surname"))
        # Preserve source field order. Locale-based reordering is an unverified transformation.
        full_name = f"{name}{' ' if language == 'en' and name and surname else ''}{surname}"

    contacts: list[str] = []
    location = ", ".join(filter(None, (_raw_text(info.get("city")), _raw_text(info.get("country")))))
    if location:
        contacts.append(f'<p class="fas fa-map-marker-alt"><span>{_text(location)}</span></p>')
    phone = " ".join(filter(None, (_raw_text(info.get("phone_prefix")), _raw_text(info.get("phone")))))
    if phone:
        contacts.append(f'<p class="fas fa-phone"><span>{_text(phone)}</span></p>')
    if _present(info.get("email")):
        contacts.append(f'<p class="fas fa-envelope"><span>{_text(info["email"])}</span></p>')
    for field_name, label, icon in (
        ("linkedin", "LinkedIn", "fab fa-linkedin"),
        ("github", "GitHub", "fab fa-github"),
        ("wechat", "微信" if language != "en" else "WeChat", "fab fa-weixin"),
    ):
        value = _raw_text(info.get(field_name))
        if value:
            if value.startswith(("http://", "https://")):
                contacts.append(f'<p class="{icon}"><a href="{_text(value)}">{label}</a></p>')
            else:
                contacts.append(f'<p class="{icon}"><span>{_text(value)}</span></p>')
    return f'<header><h1>{_text(full_name)}</h1><div class="contact-info">{"".join(contacts)}</div></header>'


def _render_education_entry(raw: Any, *, language: str) -> str:
    edu = _as_mapping(raw)
    additional = _as_mapping(edu.get("additional_info") or {})
    degree = _display_degree(edu.get("education_level"), language=language)
    major = edu.get("field_of_study")
    title = " · ".join(item for item in (degree, _text(major) if _present(major) else "") if item)
    years = " – ".join(_text(item) for item in (edu.get("start_date"), edu.get("year_of_completion")) if _present(item))
    labels = {
        "research": "研究方向" if language != "en" else "Research focus",
        "topics": "研究内容" if language != "en" else "Research topics",
        "courses": "相关课程" if language != "en" else "Relevant coursework",
        "honors": "在校荣誉" if language != "en" else "Honors",
    }
    facts: list[str] = []
    values = (
        (labels["research"], edu.get("research_direction") or additional.get("research_direction")),
        (labels["topics"], edu.get("research_topics") or additional.get("research_topics")),
        (labels["courses"], additional.get("relevant_courses") or additional.get("exam") or edu.get("exam")),
        (labels["honors"], additional.get("honors")),
    )
    for label, value in values:
        rendered = _join_values(value)
        if rendered:
            facts.append(f"<li><strong>{label}：</strong>{rendered}</li>")
    grade = edu.get("final_evaluation_grade")
    grade_html = f'<div class="grade">GPA: {_text(grade)}</div>' if _present(grade) else ""
    facts_html = f'<ul class="compact-list">{"".join(facts)}</ul>' if facts else ""
    return (
        '<div class="entry"><div class="entry-header">'
        f'<span class="entry-name">{_text(edu.get("institution")) if _present(edu.get("institution")) else ""}</span>'
        '<span class="entry-location"></span></div><div class="entry-details">'
        f'<span class="entry-title">{title}</span><span class="entry-year">{years}</span>'
        f'</div>{grade_html}{facts_html}</div>'
    )


def protect_education_section(
    education_details: Iterable[Any] | None,
    generated_html: str = "",
    *,
    language: str = "zh",
) -> EducationGuardResult:
    entries = [_render_education_entry(item, language=language) for item in (education_details or [])]
    if not entries:
        return EducationGuardResult(html="", discarded_model_output=bool(generated_html.strip()))
    heading = "教育背景" if language != "en" else "Education"
    return EducationGuardResult(
        html=f'<section id="education"><h2>{heading}</h2>{"".join(entries)}</section>',
        discarded_model_output=bool(generated_html.strip()),
    )


def _responsibilities(exp: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for item in exp.get("key_responsibilities") or []:
        if isinstance(item, Mapping):
            value = item.get("responsibility") or item.get("description") or next(iter(item.values()), "")
        else:
            value = item
        if _present(value):
            result.append(_raw_text(value))
    return result


def _render_work(experiences: Iterable[Any] | None, generated: str, language: str) -> tuple[str, list[GuardViolation]]:
    entries: list[str] = []
    violations: list[GuardViolation] = []
    for index, raw in enumerate(experiences or []):
        exp = _as_mapping(raw)
        source_bullets = _responsibilities(exp)
        bullets, blocked = _extract_safe_entry_bullets(
            generated,
            [_raw_text(exp.get("company")), _raw_text(exp.get("position"))],
            source_bullets,
            [
                *(_raw_text(skill) for skill in exp.get("skills_acquired") or [] if _present(skill)),
                _raw_text(exp.get("industry")),
                _raw_text(exp.get("position")),
            ],
            path=f"experience_details.{index}.key_responsibilities",
        )
        violations.extend(blocked)
        items = "".join(f"<li>{_text(item)}</li>" for item in bullets)
        list_html = f'<ul class="compact-list">{items}</ul>' if items else ""
        entries.append(
            '<div class="entry"><div class="entry-header">'
            f'<span class="entry-name">{_text(exp.get("company")) if _present(exp.get("company")) else ""}</span>'
            f'<span class="entry-location">{_text(exp.get("location")) if _present(exp.get("location")) else ""}</span>'
            '</div><div class="entry-details">'
            f'<span class="entry-title">{_text(exp.get("position")) if _present(exp.get("position")) else ""}</span>'
            f'<span class="entry-year">{_text(exp.get("employment_period")) if _present(exp.get("employment_period")) else ""}</span>'
            f'</div>{list_html}</div>'
        )
    if not entries:
        return "", violations
    heading = "工作经验" if language != "en" else "Experience"
    return f'<section id="work-experience"><h2>{heading}</h2>{"".join(entries)}</section>', violations


def _render_projects(projects: Iterable[Any] | None, generated: str, language: str) -> tuple[str, list[GuardViolation]]:
    entries: list[str] = []
    violations: list[GuardViolation] = []
    for index, raw in enumerate(projects or []):
        project = _as_mapping(raw)
        source = [_raw_text(project.get("description"))] if _present(project.get("description")) else []
        bullets, blocked = _extract_safe_entry_bullets(
            generated, [_raw_text(project.get("name"))], source,
            path=f"projects.{index}.description",
        )
        violations.extend(blocked)
        name = _text(project.get("name")) if _present(project.get("name")) else ""
        link = _raw_text(project.get("link"))
        name_html = f'<a href="{_text(link)}">{name}</a>' if link else name
        items = "".join(f"<li>{_text(item)}</li>" for item in bullets)
        list_html = f'<ul class="compact-list">{items}</ul>' if items else ""
        entries.append(
            '<div class="entry"><div class="entry-header">'
            f'<span class="entry-name">{name_html}</span><span class="entry-tech"></span>'
            f'</div>{list_html}</div>'
        )
    if not entries:
        return "", violations
    heading = "项目经验" if language != "en" else "Projects"
    return f'<section id="side-projects"><h2>{heading}</h2>{"".join(entries)}</section>', violations


def _render_named_list(
    items: Iterable[Any] | None,
    generated: str = "",
    *,
    section_id: str,
    heading: str,
) -> tuple[str, list[GuardViolation]]:
    rendered: list[str] = []
    violations: list[GuardViolation] = []
    generated_items = [
        item.get_text(" ", strip=True)
        for item in BeautifulSoup(generated or "", "html.parser").select("li")
    ]
    for raw in items or []:
        item = _as_mapping(raw)
        name = _raw_text(item.get("name"))
        description = _raw_text(item.get("description"))
        for candidate in generated_items:
            if name and name in candidate:
                candidate_description = candidate.split(name, 1)[1].lstrip("：:|- ")
                reasons = validate_grounded_text(f"{name} {description}", candidate_description)
                if reasons:
                    violations.append(GuardViolation(
                        f"{section_id}.{name}.description",
                        "; ".join(reasons),
                        candidate_description,
                    ))
                elif candidate_description:
                    description = candidate_description
                break
        if name or description:
            prefix = f"<strong>{_text(name)}：</strong>" if name else ""
            rendered.append(f"<li>{prefix}{_text(description)}</li>")
    if not rendered:
        return "", violations
    return f'<section id="{section_id}"><h2>{heading}</h2><ul class="compact-list">{"".join(rendered)}</ul></section>', violations


def _render_additional(
    resume: Any,
    generated: str = "",
    *,
    language: str,
) -> tuple[str, list[GuardViolation]]:
    data = _as_mapping(resume)
    violations: list[GuardViolation] = []
    skills: list[str] = []
    for raw in data.get("experience_details") or []:
        for skill in _as_mapping(raw).get("skills_acquired") or []:
            value = _raw_text(skill)
            if value and value not in skills:
                skills.append(value)
    sections: list[str] = []
    inferred_items: list[str] = []
    generated_soup = BeautifulSoup(generated or "", "html.parser")
    evidence = "\n".join(_flatten_facts(resume))
    for index, item in enumerate(generated_soup.select("#technical-stack li")):
        text = item.get_text(" ", strip=True)
        reasons = validate_grounded_text(evidence, text)
        if reasons:
            violations.append(GuardViolation(
                f"inferred_skills.{index}", "; ".join(reasons), text
            ))
        elif text:
            inferred_items.append(text)

    if skills or inferred_items:
        heading = "技能" if language != "en" else "Skills"
        label = "已确认技能" if language != "en" else "Confirmed skills"
        items = [f"<li>{_text(item)}</li>" for item in inferred_items]
        inferred_text = " ".join(inferred_items)
        missing_confirmed = [skill for skill in skills if skill.lower() not in inferred_text.lower()]
        if missing_confirmed:
            items.append(f'<li><strong>{label}：</strong>{"、".join(_text(skill) for skill in missing_confirmed)}</li>')
        sections.append(
            f'<section id="technical-stack"><h2>{heading}</h2><ul class="compact-list stack-list">'
            f'{"".join(items)}</ul></section>'
        )
    languages = []
    for raw in data.get("languages") or []:
        item = _as_mapping(raw)
        value = "（".join(filter(None, (_raw_text(item.get("language")), _raw_text(item.get("proficiency")))))
        if value and _present(item.get("proficiency")):
            value += "）"
        if value:
            languages.append(value)
    interests = [_raw_text(item) for item in data.get("interests") or [] if _present(item)]
    other: list[str] = []
    if languages:
        other.append(f'<li><strong>{"语言能力" if language != "en" else "Languages"}：</strong>{"、".join(_text(item) for item in languages)}</li>')
    if interests:
        other.append(f'<li><strong>{"兴趣爱好" if language != "en" else "Interests"}：</strong>{"、".join(_text(item) for item in interests)}</li>')
    if other:
        heading = "语言与其他" if language != "en" else "Languages & Other"
        sections.append(f'<section id="languages-other"><h2>{heading}</h2><ul class="compact-list inline-list">{"".join(other)}</ul></section>')
    return "".join(sections), violations


def _safe_summary(generated: str, resume: Any) -> tuple[str, list[GuardViolation]]:
    if not generated:
        return "", []
    text = BeautifulSoup(generated, "html.parser").get_text(" ", strip=True)
    evidence = "\n".join(_flatten_facts(resume))
    reasons = validate_grounded_text(evidence, text)
    if reasons:
        return "", [GuardViolation("professional_summary", "; ".join(reasons), text)]
    return generated, []


def _replace_node_text(node: Any, value: Any) -> None:
    """Replace a locked field without changing the surrounding DOM structure."""

    if node is None:
        return
    node.clear()
    if _present(value):
        node.append(str(value).strip())


def _copy_contents(target: Any, source: Any) -> None:
    target.clear()
    for child in list(source.contents):
        target.append(child)


def _section_root(soup: BeautifulSoup) -> Any:
    return soup.find("section") or soup


def _canonical_entry(html: str) -> Any | None:
    return BeautifulSoup(html, "html.parser").select_one(".entry")


def _assign_entries(entries: list[Any], sources: list[dict[str, Any]], anchor_fields: tuple[str, ...]) -> dict[int, Any]:
    """Match by immutable anchors when possible, then fall back to source order."""

    assigned: dict[int, Any] = {}
    unused = list(entries)
    for index, source in enumerate(sources):
        anchors = [_raw_text(source.get(field)) for field in anchor_fields if _present(source.get(field))]
        matched = next(
            (entry for entry in unused if anchors and all(anchor in entry.get_text(" ", strip=True) for anchor in anchors)),
            None,
        )
        if matched is None and unused:
            matched = unused[0]
        if matched is not None:
            assigned[index] = matched
            unused.remove(matched)
    for entry in unused:
        entry.decompose()
    return assigned


def _patch_header_in_place(generated: str, personal: Any, *, language: str) -> str:
    if not generated.strip():
        return _render_header(personal, language=language)
    info = _as_mapping(personal)
    soup = BeautifulSoup(generated, "html.parser")
    header = soup.find("header")
    if header is None:
        return _render_header(personal, language=language)

    full_name = _raw_text(info.get("full_name"))
    if not full_name:
        name, surname = _raw_text(info.get("name")), _raw_text(info.get("surname"))
        full_name = f"{name}{' ' if language == 'en' and name and surname else ''}{surname}"
    heading = header.find("h1")
    if heading is None:
        heading = soup.new_tag("h1")
        header.insert(0, heading)
    _replace_node_text(heading, full_name)

    values = {
        "fa-map-marker-alt": ", ".join(filter(None, (_raw_text(info.get("city")), _raw_text(info.get("country"))))),
        "fa-phone": " ".join(filter(None, (_raw_text(info.get("phone_prefix")), _raw_text(info.get("phone"))))),
        "fa-envelope": _raw_text(info.get("email")),
        "fa-linkedin": _raw_text(info.get("linkedin")),
        "fa-github": _raw_text(info.get("github")),
        "fa-weixin": _raw_text(info.get("wechat")),
    }
    seen: set[str] = set()
    for item in list(header.select(".contact-info p")):
        classes = set(item.get("class") or [])
        key = next((candidate for candidate in values if candidate in classes), None)
        if key is None or not values[key]:
            item.decompose()
            continue
        seen.add(key)
        value = values[key]
        target = item.find("a") or item.find("span") or item
        if target.name == "a" and value.startswith(("http://", "https://")):
            target["href"] = value
            _replace_node_text(target, "LinkedIn" if key == "fa-linkedin" else "GitHub")
        else:
            if target.name == "a":
                target.attrs.pop("href", None)
            _replace_node_text(target, value)
    for link in list(header.find_all("a", href=True)):
        if link.find_parent("p") is None:
            link.decompose()
    contact_info = header.select_one(".contact-info")
    if contact_info is None:
        contact_info = soup.new_tag("div", attrs={"class": "contact-info"})
        header.append(contact_info)
    canonical = BeautifulSoup(_render_header(personal, language=language), "html.parser")
    for item in canonical.select(".contact-info p"):
        classes = set(item.get("class") or [])
        key = next((candidate for candidate in values if candidate in classes), None)
        if key is not None and key not in seen:
            contact_info.append(item)
    return str(soup)


def _patch_education_in_place(generated: str, education: Iterable[Any] | None, *, language: str) -> str:
    sources = [_as_mapping(item) for item in (education or [])]
    if not sources:
        return ""
    if not generated.strip():
        return protect_education_section(sources, language=language).html
    soup = BeautifulSoup(generated, "html.parser")
    root = _section_root(soup)
    entries = list(root.select(".entry"))
    assigned = _assign_entries(entries, sources, ("institution", "field_of_study"))
    for index, source in enumerate(sources):
        canonical = _canonical_entry(_render_education_entry(source, language=language))
        entry = assigned.get(index)
        if entry is None:
            if canonical is not None:
                canonical["data-source-id"] = f"education-{index}"
                root.append(canonical)
            continue
        entry["data-source-id"] = f"education-{index}"
        for selector in (".entry-name", ".entry-location", ".entry-title", ".entry-year", ".grade", "ul.compact-list"):
            current, locked = entry.select_one(selector), canonical.select_one(selector) if canonical else None
            if current is not None and locked is not None:
                _copy_contents(current, locked)
            elif current is not None:
                current.decompose()
            elif locked is not None:
                entry.append(locked)
    return str(soup)


def _filter_entry_claims(entry: Any, evidence: str, *, path: str) -> list[GuardViolation]:
    violations: list[GuardViolation] = []
    for item in list(entry.select("li")):
        candidate = item.get_text(" ", strip=True)
        reasons = validate_grounded_text(evidence, candidate)
        if reasons:
            violations.append(GuardViolation(path, "; ".join(reasons), candidate))
            item.decompose()
    return violations


def _patch_work_in_place(generated: str, experiences: Iterable[Any] | None, *, language: str) -> tuple[str, list[GuardViolation]]:
    sources = [_as_mapping(item) for item in (experiences or [])]
    if not sources:
        return "", []
    if not generated.strip():
        return _render_work(sources, "", language)
    soup = BeautifulSoup(generated, "html.parser")
    root = _section_root(soup)
    assigned = _assign_entries(list(root.select(".entry")), sources, ("company", "position"))
    violations: list[GuardViolation] = []
    selectors = {
        ".entry-name": "company", ".entry-location": "location",
        ".entry-title": "position", ".entry-year": "employment_period",
    }
    for index, source in enumerate(sources):
        entry = assigned.get(index)
        if entry is None:
            fallback, _ = _render_work([source], "", language)
            node = _canonical_entry(fallback)
            if node is not None:
                node["data-source-id"] = f"experience-{index}"
                root.append(node)
            continue
        entry["data-source-id"] = f"experience-{index}"
        for selector, field in selectors.items():
            _replace_node_text(entry.select_one(selector), source.get(field))
        evidence = "\n".join(_flatten_facts(source))
        violations.extend(_filter_entry_claims(
            entry, evidence, path=f"experience_details.{index}.key_responsibilities"
        ))
        if not entry.select("li") and _responsibilities(source):
            target_list = entry.find("ul")
            if target_list is None:
                target_list = soup.new_tag("ul", attrs={"class": "compact-list"})
                entry.append(target_list)
            for responsibility in _responsibilities(source):
                item = soup.new_tag("li")
                item.string = responsibility
                target_list.append(item)
    return str(soup), violations


def _patch_projects_in_place(generated: str, projects: Iterable[Any] | None, *, language: str) -> tuple[str, list[GuardViolation]]:
    sources = [_as_mapping(item) for item in (projects or [])]
    if not sources:
        return "", []
    if not generated.strip():
        return _render_projects(sources, "", language)
    soup = BeautifulSoup(generated, "html.parser")
    root = _section_root(soup)
    assigned = _assign_entries(list(root.select(".entry")), sources, ("name",))
    violations: list[GuardViolation] = []
    for index, source in enumerate(sources):
        entry = assigned.get(index)
        if entry is None:
            fallback, _ = _render_projects([source], "", language)
            node = _canonical_entry(fallback)
            if node is not None:
                node["data-source-id"] = f"project-{index}"
                root.append(node)
            continue
        entry["data-source-id"] = f"project-{index}"
        name_container = entry.select_one(".entry-name")
        link = _raw_text(source.get("link"))
        name_target = name_container.find("a") if name_container else None
        if name_target is not None:
            _replace_node_text(name_target, source.get("name"))
            if link:
                name_target["href"] = link
            else:
                name_target.attrs.pop("href", None)
        elif name_container is not None:
            _replace_node_text(name_container, source.get("name"))
        evidence = "\n".join(_flatten_facts(source))
        violations.extend(_filter_entry_claims(entry, evidence, path=f"projects.{index}.description"))
        if not entry.select("li") and _present(source.get("description")):
            target_list = entry.find("ul")
            if target_list is None:
                target_list = soup.new_tag("ul", attrs={"class": "compact-list"})
                entry.append(target_list)
            item = soup.new_tag("li")
            item.string = _raw_text(source.get("description"))
            target_list.append(item)
    return str(soup), violations


def _patch_named_list_in_place(
    generated: str,
    items: Iterable[Any] | None,
    *,
    section_id: str,
    heading: str,
) -> tuple[str, list[GuardViolation]]:
    sources = [_as_mapping(item) for item in (items or [])]
    if not sources:
        return "", []
    if not generated.strip():
        return _render_named_list(sources, section_id=section_id, heading=heading)
    soup = BeautifulSoup(generated, "html.parser")
    root = _section_root(soup)
    candidates = list(root.select("li"))
    assigned = _assign_entries(candidates, sources, ("name",))
    violations: list[GuardViolation] = []
    for index, source in enumerate(sources):
        item = assigned.get(index)
        if item is None:
            fallback, _ = _render_named_list([source], section_id=section_id, heading=heading)
            fallback_item = BeautifulSoup(fallback, "html.parser").find("li")
            target_list = root.find("ul") or root
            if fallback_item is not None:
                fallback_item["data-source-id"] = f"{section_id}-{index}"
                target_list.append(fallback_item)
            continue
        item["data-source-id"] = f"{section_id}-{index}"
        strong = item.find("strong")
        if strong is None:
            strong = soup.new_tag("strong")
            item.insert(0, strong)
        _replace_node_text(strong, f"{_raw_text(source.get('name'))}：")
        reasons = validate_grounded_text(
            " ".join(filter(None, (_raw_text(source.get("name")), _raw_text(source.get("description"))))),
            item.get_text(" ", strip=True),
        )
        if reasons:
            violations.append(GuardViolation(
                f"{section_id}.{index}.description", "; ".join(reasons), item.get_text(" ", strip=True)
            ))
            _copy_contents(item, BeautifulSoup(
                f'<li><strong>{_text(source.get("name"))}：</strong>{_text(source.get("description"))}</li>',
                "html.parser",
            ).find("li"))
    return str(soup), violations


def _patch_additional_in_place(generated: str, resume: Any, *, language: str) -> tuple[str, list[GuardViolation]]:
    if not generated.strip():
        return _render_additional(resume, "", language=language)
    soup = BeautifulSoup(generated, "html.parser")
    evidence = "\n".join(_flatten_facts(resume))
    violations: list[GuardViolation] = []
    technical = soup.select_one("#technical-stack")
    if technical is not None:
        violations.extend(_filter_entry_claims(technical, evidence, path="inferred_skills"))

    data = _as_mapping(resume)
    languages = []
    for raw in data.get("languages") or []:
        item = _as_mapping(raw)
        value = "：".join(filter(None, (_raw_text(item.get("language")), _raw_text(item.get("proficiency")))))
        if value:
            languages.append(value)
    interests = [_raw_text(item) for item in data.get("interests") or [] if _present(item)]
    for item in list(soup.select("#languages-other li")):
        label = (item.find("strong").get_text(" ", strip=True) if item.find("strong") else "").lower()
        if "语言" in label or "language" in label:
            value = "、".join(languages)
        elif "兴趣" in label or "interest" in label:
            value = "、".join(interests)
        else:
            item.decompose()
            continue
        if not value:
            item.decompose()
            continue
        strong = item.find("strong")
        label_html = str(strong) if strong else ""
        item.clear()
        if label_html:
            item.append(BeautifulSoup(label_html, "html.parser").find("strong"))
        item.append(value)
    return str(soup), violations


def protect_resume_sections(
    resume: Any,
    generated_sections: Mapping[str, str] | None = None,
    *,
    language: str = "zh",
) -> ResumeGuardResult:
    """Patch hard facts in place while retaining generated HTML and soft content.

    Identity, education, employment metadata, project names/links and named
    credentials come from source data. Generated section/entry/list markup is
    retained; only new numeric/contact claims are removed from prose.
    """

    generated = dict(generated_sections or {})
    data = _as_mapping(resume)
    violations: list[GuardViolation] = []
    education = _patch_education_in_place(
        generated.get("education", ""), data.get("education_details"), language=language
    )
    work, work_violations = _patch_work_in_place(
        generated.get("work_experience", ""), data.get("experience_details"), language=language
    )
    projects, project_violations = _patch_projects_in_place(
        generated.get("projects", ""), data.get("projects"), language=language
    )
    summary, summary_violations = _safe_summary(generated.get("summary", ""), resume)
    violations.extend(work_violations)
    violations.extend(project_violations)
    violations.extend(summary_violations)

    achievements_heading = "成就荣誉" if language != "en" else "Achievements"
    academic_heading = "学术成果" if language != "en" else "Academic Output"
    certifications_heading = "证书资质" if language != "en" else "Certifications"
    achievements, achievement_violations = _patch_named_list_in_place(
        generated.get("achievements", ""),
        data.get("achievements"),
        section_id="achievements",
        heading=achievements_heading,
    )
    academic_achievements, academic_violations = _patch_named_list_in_place(
        generated.get("academic_achievements", ""),
        [
            {"name": item.get("title", ""), "description": " | ".join(
                str(item.get(field, "")).strip()
                for field in ("type", "authors", "venue", "date", "status", "description", "link")
                if str(item.get(field, "")).strip()
            )}
            for item in (data.get("academic_achievements") or [])
            if isinstance(item, Mapping) and str(item.get("title", "")).strip()
        ],
        section_id="academic-achievements",
        heading=academic_heading,
    )
    certifications, certification_violations = _patch_named_list_in_place(
        generated.get("certifications", ""),
        data.get("certifications"),
        section_id="certifications",
        heading=certifications_heading,
    )
    additional, additional_violations = _patch_additional_in_place(
        generated.get("additional_skills", ""),
        resume,
        language=language,
    )
    violations.extend(achievement_violations)
    violations.extend(academic_violations)
    violations.extend(certification_violations)
    violations.extend(additional_violations)
    sections = {
        "header": _patch_header_in_place(
            generated.get("header", ""), data.get("personal_information"), language=language
        ),
        "summary": summary,
        "education": education,
        "work_experience": work,
        "projects": projects,
        "academic_achievements": academic_achievements,
        "achievements": achievements,
        "certifications": certifications,
        "additional_skills": additional,
    }
    return ResumeGuardResult(sections=sections, violations=violations)
