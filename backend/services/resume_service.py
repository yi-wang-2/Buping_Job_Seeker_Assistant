"""Resume generation service — wraps existing src/ logic."""

from __future__ import annotations

import base64
import html as html_lib
import logging
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any, Callable

import yaml

from backend.services.config_service import load_secrets, save_secrets

logger = logging.getLogger(__name__)

DATA_FOLDER = Path("data_folder")
OUTPUT_FOLDER = DATA_FOLDER / "output"
STYLES_DIR = Path("src/libs/resume_and_cover_builder/resume_style")

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

_GENERATION_PROGRESS: dict[str, dict[str, Any]] = {}
_GENERATION_PROGRESS_LOCK = threading.Lock()


def update_generation_progress(
    request_id: str,
    progress: int,
    stage: str,
    detail: str = "",
    *,
    status: str = "running",
) -> None:
    """Record a real generation milestone for frontend polling."""

    if not request_id:
        return
    now = time.time()
    with _GENERATION_PROGRESS_LOCK:
        stale = [key for key, value in _GENERATION_PROGRESS.items() if now - value.get("updated_at", now) > 3600]
        for key in stale:
            _GENERATION_PROGRESS.pop(key, None)
        current = _GENERATION_PROGRESS.get(request_id, {})
        events = list(current.get("events", []))
        event = {"progress": max(0, min(100, int(progress))), "stage": stage, "detail": detail}
        if not events or events[-1] != event:
            events.append(event)
        _GENERATION_PROGRESS[request_id] = {
            **event,
            "status": status,
            "updated_at": now,
            "events": events[-40:],
        }


def get_generation_progress(request_id: str) -> dict[str, Any] | None:
    with _GENERATION_PROGRESS_LOCK:
        value = _GENERATION_PROGRESS.get(request_id)
        if value is None:
            return None
        return {**value, "events": [dict(event) for event in value.get("events", [])]}


def cleanup_public_artifacts(max_age_seconds: int = 3600) -> None:
    """Remove expired, unguessable public-demo PDF/HTML artifacts."""
    cutoff = time.time() - max_age_seconds
    for pattern in ("public_*.pdf", "public_*.html"):
        for artifact in OUTPUT_FOLDER.glob(pattern):
            try:
                if artifact.stat().st_mtime < cutoff:
                    artifact.unlink()
            except OSError:
                pass


# Lightweight preview HTML template — used by preview_resume() to render
# the local YAML resume without invoking the LLM.
PREVIEW_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="$lang">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Resume Preview</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.3/css/all.min.css" />
<style>
$style_css
.preview-only-hint { display:none; }
</style>
</head>
<body>
$body
</body>
</html>"""


def _escape(value: Any) -> str:
    """Safely escape a value for HTML rendering."""
    if value is None:
        return ""
    return html_lib.escape(str(value))


def _render_resume_preview_body(data: dict[str, Any], language: str = "zh") -> str:
    """Render the resume YAML data into a simple HTML body for preview.

    This deliberately avoids invoking the LLM so the preview can be
    generated in milliseconds. The visual style is governed by the
    selected CSS template, the body content is rendered from the local
    YAML resume.
    """
    parts: list[str] = []

    personal = data.get("personal_information") or {}
    if personal:
        confirmed_name = personal.get("full_name")
        if confirmed_name:
            full_name = _escape(confirmed_name)
        else:
            name = _escape(personal.get("name") or "")
            surname = _escape(personal.get("surname") or "")
            separator = " " if language == "en" and name and surname else ""
            full_name = f"{name}{separator}{surname}"
        contact_items: list[str] = []
        if personal.get("phone"):
            contact_items.append(
                f'<span class="preview-contact-item"><i class="fa fa-phone"></i> '
                f'{_escape(personal.get("phone_prefix") or "")} {_escape(personal["phone"])}</span>'
            )
        if personal.get("email"):
            contact_items.append(
                f'<span class="preview-contact-item"><i class="fa fa-envelope"></i> '
                f'{_escape(personal["email"])}</span>'
            )
        if personal.get("address") or personal.get("city") or personal.get("country"):
            location = ", ".join(
                _escape(x)
                for x in [personal.get("city"), personal.get("country")]
                if x
            )
            if location:
                contact_items.append(
                    f'<span class="preview-contact-item"><i class="fa fa-map-marker-alt"></i> '
                    f'{location}</span>'
                )
        for key, icon in [("github", "fa-github"), ("linkedin", "fa-linkedin"), ("wechat", "fa-weixin")]:
            val = personal.get(key)
            if val:
                contact_items.append(
                    f'<span class="preview-contact-item"><i class="fa {icon}"></i> '
                    f'{_escape(val)}</span>'
                )
        parts.append(
            f'<header class="preview-header"><h1>{full_name}</h1>'
            f'<div class="preview-contact">{"".join(contact_items)}</div></header>'
        )

    # Summary / objective (custom field supported by many users)
    summary = data.get("professional_summary") or data.get("summary") or data.get("objective")
    if summary:
        parts.append(
            f'<section><h2>Summary</h2><p class="preview-summary">{_escape(summary)}</p></section>'
        )

    experiences = data.get("experience_details") or []
    if experiences:
        items = []
        for exp in experiences:
            responsibilities = exp.get("key_responsibilities") or []
            resp_html = ""
            if responsibilities:
                if isinstance(responsibilities, list):
                    resp_html = "<ul>" + "".join(
                        f"<li>{_escape(r.get('description') if isinstance(r, dict) else r)}</li>"
                        for r in responsibilities
                    ) + "</ul>"
                else:
                    resp_html = f"<p>{_escape(responsibilities)}</p>"
            skills = exp.get("skills_acquired") or []
            skills_html = ""
            if skills:
                skills_html = (
                    '<div class="preview-skills"><strong>Skills:</strong> '
                    + ", ".join(_escape(s) for s in skills)
                    + "</div>"
                )
            items.append(
                f'<div class="preview-item">'
                f'<div class="preview-item-head">'
                f'<span class="preview-item-title">{_escape(exp.get("position") or "")}</span>'
                f'<span class="preview-item-period">{_escape(exp.get("employment_period") or "")}</span>'
                f'</div>'
                f'<div class="preview-item-sub">{_escape(exp.get("company") or "")}'
                f' &middot; {_escape(exp.get("location") or "")}</div>'
                f'{resp_html}{skills_html}'
                f'</div>'
            )
        parts.append(f'<section><h2>Experience</h2>{"".join(items)}</section>')

    education = data.get("education_details") or []
    if education:
        items = []
        for edu in education:
            additional = edu.get("additional_info") or {}
            education_facts: list[str] = []
            for label, value in (
                ("研究方向" if language != "en" else "Research focus", edu.get("research_direction") or additional.get("research_direction")),
                ("研究内容" if language != "en" else "Research topics", edu.get("research_topics") or additional.get("research_topics")),
            ):
                if value:
                    rendered = "、".join(_escape(item) for item in value) if isinstance(value, list) else _escape(value)
                    education_facts.append(f'<li><strong>{label}：</strong>{rendered}</li>')
            facts_html = f'<ul class="compact-list">{"".join(education_facts)}</ul>' if education_facts else ""
            items.append(
                f'<div class="preview-item">'
                f'<div class="preview-item-head">'
                f'<span class="preview-item-title">{_escape(edu.get("institution") or "")}</span>'
                f'<span class="preview-item-period">'
                f'{_escape(edu.get("start_date") or "")} &ndash; {_escape(edu.get("year_of_completion") or "")}'
                f'</span></div>'
                f'<div class="preview-item-sub">{_escape(edu.get("education_level") or "")} '
                f'&middot; {_escape(edu.get("field_of_study") or "")}</div>'
                f'{facts_html}'
                f'</div>'
            )
        parts.append(f'<section><h2>Education</h2>{"".join(items)}</section>')

    projects = data.get("projects") or []
    if projects:
        items = []
        for proj in projects:
            link_html = ""
            if proj.get("link"):
                link_html = (
                    f' <a href="{_escape(proj["link"])}" target="_blank" rel="noreferrer">'
                    f'{_escape(proj["link"])}</a>'
                )
            items.append(
                f'<div class="preview-item">'
                f'<div class="preview-item-title">{_escape(proj.get("name") or "")}{link_html}</div>'
                f'<p>{_escape(proj.get("description") or "")}</p>'
                f'</div>'
            )
        parts.append(f'<section><h2>Projects</h2>{"".join(items)}</section>')

    achievements = data.get("achievements") or []
    if achievements:
        items = "".join(
            f'<div class="preview-item"><div class="preview-item-title">{_escape(a.get("name") or "")}</div>'
            f'<p>{_escape(a.get("description") or "")}</p></div>'
            for a in achievements
        )
        parts.append(f'<section><h2>Achievements</h2>{items}</section>')

    certs = data.get("certifications") or []
    if certs:
        items = "".join(
            f'<div class="preview-item"><div class="preview-item-title">{_escape(c.get("name") or "")}</div>'
            f'<p>{_escape(c.get("description") or "")}</p></div>'
            for c in certs
        )
        parts.append(f'<section><h2>Certifications</h2>{items}</section>')

    languages = data.get("languages") or []
    if languages:
        items = ", ".join(
            f"{_escape(l.get('language') or '')} ({_escape(l.get('proficiency') or '')})"
            for l in languages
        )
        parts.append(f'<section><h2>Languages</h2><p>{items}</p></section>')

    interests = data.get("interests") or []
    if interests:
        items = ", ".join(_escape(i) for i in interests)
        parts.append(f'<section><h2>Interests</h2><p>{items}</p></section>')

    if not parts:
        parts.append(
            '<section><p class="preview-empty">'
            'No resume content found. Please fill in <code>data_folder/plain_text_resume.yaml</code> '
            'and try again.</p></section>'
        )

    return "".join(parts)


def generate_preview_html(
    style_name: str,
    resume_language: str = "zh",
    resume_content: str = "",
) -> dict[str, Any]:
    """Generate a lightweight HTML preview from the local YAML resume.

    Unlike ``generate_resume``, this does NOT invoke the LLM — it renders
    the YAML data with the selected CSS template so users can see how
    their resume will look in a specific style within seconds.

    Returns ``{"html": str, "style": str, "language": str}``.
    """
    from src.libs.resume_and_cover_builder import StyleManager

    # Load the YAML resume (without LLM).
    resume_file = DATA_FOLDER / (
        "plain_text_resume.yaml" if resume_language == "en" else "plain_text_resume_zh.yaml"
    )
    if not resume_file.exists():
        raise FileNotFoundError(f"Resume file not found: {resume_file}")
    if resume_content.strip():
        yaml_text = resume_content
    else:
        with open(resume_file, "r", encoding="utf-8") as f:
            yaml_text = f.read()
    data = yaml.safe_load(yaml_text) or {}

    # Resolve style CSS.
    style_manager = StyleManager()
    available_styles = style_manager.get_styles()
    chosen = style_name if style_name in available_styles else None
    if chosen is None and available_styles:
        chosen = list(available_styles.keys())[0]
    if chosen is None:
        raise RuntimeError("No resume styles available.")
    style_manager.set_selected_style(chosen)
    style_path = style_manager.get_style_path()
    if style_path is None or not style_path.exists():
        raise FileNotFoundError(f"Style file not found for: {chosen}")
    with open(style_path, "r", encoding="utf-8") as f:
        style_css = f.read()

    body_html = _render_resume_preview_body(data, resume_language)
    lang_attr = "en" if resume_language == "en" else "zh"
    full_html = Template(PREVIEW_HTML_TEMPLATE).substitute(
        body=body_html,
        style_css=style_css,
        lang=lang_attr,
    )
    return {"html": full_html, "style": chosen, "language": resume_language}


def get_available_styles() -> dict[str, dict[str, str]]:
    """Get available resume CSS styles."""
    from src.libs.resume_and_cover_builder import StyleManager

    style_manager = StyleManager()
    raw_styles = style_manager.get_styles()
    styles: dict[str, dict[str, str]] = {}
    for name, (file_name, author_link) in raw_styles.items():
        styles[name] = {"file": file_name, "author": author_link}
    return styles


def _sanitize_edited_resume_html(html_content: str) -> str:
    """Remove transient WYSIWYG state while preserving resume styling."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_content, "html.parser")
    # Browser-native list commands create unclassified lists with the user
    # agent's much wider default indentation. Generated resume lists use the
    # template's compact-list spacing, so normalize edited and legacy saves to
    # that same contract before preview/PDF persistence.
    for list_element in soup.select("section ul:not(.compact-list):not(.stack-list):not(.inline-list), section ol:not(.compact-list):not(.stack-list):not(.inline-list)"):
        list_element["class"] = [*(list_element.get("class") or []), "compact-list"]
        parent = list_element.parent
        if parent is not None and getattr(parent, "name", None) == "p":
            parent.insert_after(list_element.extract())
            if not parent.get_text(strip=True) and not parent.find(True):
                parent.decompose()
    nested_documents = list(soup.body.find_all("html")) if soup.body is not None else []
    if nested_documents:
        soup = BeautifulSoup(str(nested_documents[-1]), "html.parser")
    # Older generators could also place a <body> fragment inside the template body.
    while soup.body is not None:
        nested_body = soup.body.find("body")
        if nested_body is None:
            break
        outer_body = soup.body
        children = list(nested_body.contents)
        outer_body.clear()
        for child in children:
            outer_body.append(child.extract())
    editor_style = soup.find(id="buping-editor-style")
    if editor_style:
        editor_style.decompose()
    page_guide_style = soup.find(id="buping-page-guide-style")
    if page_guide_style:
        page_guide_style.decompose()
    page_guides = soup.find(id="buping-page-guides")
    if page_guides:
        page_guides.decompose()
    print_emulation = soup.find(id="buping-print-layout-emulation")
    if print_emulation:
        print_emulation.decompose()
    viewport_fit = soup.find(id="buping-viewport-fit")
    if viewport_fit:
        viewport_fit.decompose()
    target_page_layout = soup.find(id="buping-target-page-layout")
    if target_page_layout:
        target_page_layout.decompose()
    for empty_section in soup.select('[data-buping-all-entries-removed="true"]'):
        empty_section.attrs.pop("data-buping-all-entries-removed", None)
        empty_section.attrs["data-buping-library-empty-section"] = "true"
        empty_section.attrs["hidden"] = ""
    for editor_only in soup.select("[data-buping-entry-action], [data-buping-module-action], [data-buping-empty-placeholder]"):
        editor_only.decompose()
    for element in soup.select(
        "[data-buping-block], [data-buping-removable-entry], [data-buping-module], [data-buping-empty-field], [contenteditable]"
    ):
        element.attrs.pop("data-buping-block", None)
        element.attrs.pop("data-buping-removable-entry", None)
        element.attrs.pop("data-buping-module", None)
        element.attrs.pop("data-buping-empty-field", None)
        element.attrs.pop("data-buping-all-entries-removed", None)
        element.attrs.pop("contenteditable", None)
    for page_break in soup.select("[data-buping-page-break]"):
        page_break.decompose()
    return str(soup)


def render_html_to_pdf_bytes(html_content: str) -> bytes:
    """Render HTML with the exact same Chrome print pipeline used for downloads."""
    import base64 as _b64
    from src.utils.chrome_utils import HTML_to_PDF, init_browser

    sanitized_html = _sanitize_edited_resume_html(html_content)
    driver = init_browser()
    try:
        return _b64.b64decode(HTML_to_PDF(sanitized_html, driver))
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def count_pdf_pages(pdf_data: bytes) -> int:
    """Count actual PDF pages using the project's existing pdfminer dependency."""

    from io import BytesIO
    from pdfminer.pdfpage import PDFPage

    return sum(1 for _ in PDFPage.get_pages(BytesIO(pdf_data)))


def apply_target_page_layout(
    html_content: str, spacing_factor: float, *, stretch_pages: int = 0
) -> str:
    """Fit density using the editor's line-height and module-spacing controls."""

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_sanitize_edited_resume_html(html_content), "html.parser")
    existing = soup.find("style", id="buping-target-page-layout")
    if existing is not None:
        existing.decompose()
    saved_controls = soup.find("style", id="buping-layout-controls")
    style_text = "\n".join(style.get_text() for style in soup.find_all("style"))
    saved_line_height = float(saved_controls.get("data-line-height", 0) or 0) if saved_controls else 0
    saved_module_spacing = float(saved_controls.get("data-module-spacing", 0) or 0) if saved_controls else 0
    if saved_line_height <= 0:
        match = re.search(r"body\s*\{[^}]*line-height:\s*([0-9.]+)", style_text, re.DOTALL)
        saved_line_height = float(match.group(1)) if match else 1.32
    if saved_module_spacing <= 0:
        match = re.search(r"\.entry\s*\{[^}]*margin-bottom:\s*([0-9.]+)px", style_text, re.DOTALL)
        saved_module_spacing = float(match.group(1)) if match else 8.0
    base_line_height = max(1.1, min(1.7, saved_line_height))
    base_module_spacing = max(2.0, min(20.0, saved_module_spacing))
    if saved_controls is not None:
        saved_controls.decompose()
    if soup.head is None:
        html_tag = soup.html or soup.new_tag("html")
        if soup.html is None:
            html_tag.extend(list(soup.contents))
            soup.append(html_tag)
        head = soup.new_tag("head")
        html_tag.insert(0, head)
    spacing_factor = max(0.0, min(1.35, spacing_factor))
    if spacing_factor <= 1.0:
        line_height = 1.1 + (base_line_height - 1.1) * spacing_factor
        module_spacing = 2.0 + (base_module_spacing - 2.0) * spacing_factor
    else:
        expansion = (spacing_factor - 1.0) / 0.35
        line_height = base_line_height + (1.7 - base_line_height) * expansion
        module_spacing = base_module_spacing + (20.0 - base_module_spacing) * expansion
    line_height = max(1.1, min(1.7, line_height))
    module_spacing = max(2.0, min(20.0, module_spacing))
    list_spacing = max(1, round(module_spacing / 4))
    title_top = max(4, module_spacing + 2)
    title_bottom = max(2, round(module_spacing / 2))
    entry_padding_y = max(4, round(module_spacing * 0.75))
    header_spacing = max(6, module_spacing + 2)

    controls = soup.new_tag("style", id="buping-layout-controls")
    controls["data-line-height"] = f"{line_height:.4f}"
    controls["data-module-spacing"] = f"{module_spacing:.4f}"
    controls.string = f"""
body {{ line-height: {line_height:.4f} !important; }}
header {{ margin-bottom: {header_spacing:.2f}px !important; }}
h2 {{ margin-top: {title_top:.2f}px !important; margin-bottom: {title_bottom:.2f}px !important; }}
.entry, .resume-card {{
  margin-bottom: {module_spacing:.2f}px !important;
  padding-top: {entry_padding_y:.2f}px !important;
  padding-bottom: {entry_padding_y:.2f}px !important;
}}
.compact-list, .stack-list, .inline-list {{
  margin-top: {list_spacing}px !important;
  margin-bottom: {list_spacing}px !important;
}}
.compact-list li, .stack-list li, .inline-list li {{ margin-bottom: {list_spacing}px !important; }}
"""
    soup.head.append(controls)

    style = soup.new_tag("style", id="buping-target-page-layout")
    stretch_css = ""
    if stretch_pages:
        logical_height = stretch_pages * 1123.0
        stretch_css = f"""
:root > body {{ min-height: {logical_height:.2f}px !important; display: flex !important;
  flex-direction: column !important; justify-content: space-between !important; }}
"""
    style.string = f"""
:root > body {{
  --buping-spacing-factor: {spacing_factor:.5f};
  --buping-line-height: {line_height:.4f};
  --buping-module-spacing: {module_spacing:.4f}px;
  width: auto !important;
  max-width: 700px !important;
  margin-left: auto !important;
  margin-right: auto !important;
  box-sizing: border-box !important;
}}
{stretch_css}
"""
    soup.head.append(style)
    return str(soup)


def _strip_html_code_fence(value: str) -> str:
    value = value.strip()
    match = re.fullmatch(r"```(?:html)?\s*(.*?)\s*```", value, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else value


def _resume_structure_counts(html_content: str) -> dict[str, int]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_content, "html.parser")
    counts = {
        "header": len(soup.select("header")),
        "entries": len(soup.select(".entry")),
        "bullets": len(soup.select("li")),
    }
    for section_id in _REGENERATABLE_SECTION_IDS - {"header"}:
        counts[section_id] = len(soup.select(f"#{section_id}"))
    return counts


def _resume_visible_text_length(html_content: str) -> int:
    from bs4 import BeautifulSoup

    return len(BeautifulSoup(html_content, "html.parser").get_text(" ", strip=True))


def condense_resume_html_with_llm(
    html_content: str,
    resume: Any,
    api_key: str,
    *,
    language: str = "zh",
    target_pages: int = 1,
    editable_targets: list[str] | None = None,
    target_text_ratio: float = 0.7,
) -> tuple[str, bool]:
    """Shorten descriptive copy while preserving DOM structure and hard facts."""

    from bs4 import BeautifulSoup
    from src.libs.ai_engine.harness import protect_hard_facts_in_place
    from src.libs.resume_and_cover_builder.llm.llm_generate_resume import _create_gateway_chat_model

    original = BeautifulSoup(_sanitize_edited_resume_html(html_content), "html.parser")
    original_body = original.body
    original_main = original.find("main")
    if original_body is None or original_main is None:
        return html_content, True
    prompt_language = "Chinese" if language.startswith("zh") else "English"
    target_text_ratio = max(0.25, min(0.82, target_text_ratio))
    target_density = f"{round(target_text_ratio * 100)}%-{round(min(0.9, target_text_ratio + 0.08) * 100)}%"
    current_visible_chars = len(original_main.get_text(" ", strip=True))
    maximum_visible_chars = max(600, round(current_visible_chars * target_text_ratio))
    target_rule = (
        f"Only edit these selected targets: {', '.join(editable_targets)}."
        if editable_targets
        else "All descriptive modules may be shortened."
    )
    prompt = f"""You are compressing a resume that still exceeds its requested {target_pages}-page PDF target after spacing was minimized.
Return only the inner HTML of <main>, in {prompt_language}. Do not return Markdown fences.

Rules:
1. Keep every section, experience, project, education entry, list item, project name, employer, school, title, date, location, contact detail and number.
2. Keep the existing HTML structure, ids, classes, order and formatting exactly; edit text inside descriptive paragraphs/list items only.
3. Shorten repetition and low-value modifiers. Preserve action, method, result and meaningful evidence.
4. Never merge, delete, rename or exchange entries. Never invent information.
5. Aim for roughly {target_density} of the current descriptive text length. Prefer concise clauses over removing any fact or bullet.
6. {target_rule}
7. Hard limit: the returned visible text inside <main> must not exceed {maximum_visible_chars} characters (currently {current_visible_chars}).

CURRENT MAIN HTML:
{original_main.decode_contents()}
"""
    client = _create_gateway_chat_model(api_key, skill="resume_layout_compactor", max_output_tokens=8000)
    response = client.invoke([{"role": "user", "content": prompt}])
    candidate_text = _strip_html_code_fence(str(getattr(response, "content", response)))
    candidate_fragment = BeautifulSoup(candidate_text, "html.parser")
    candidate_main = candidate_fragment.find("main") or candidate_fragment

    replacement_doc = BeautifulSoup(str(original), "html.parser")
    replacement_main = replacement_doc.find("main")
    if replacement_main is None:
        return html_content, True
    replacement_main.clear()
    for child in list(candidate_main.contents):
        replacement_main.append(child.extract())
    if editable_targets:
        # Partial regeneration locks every unselected node. Reuse the same
        # deterministic DOM merge so layout compaction cannot bypass that lock.
        replacement_doc = BeautifulSoup(
            merge_regenerated_resume_html(str(original), str(replacement_doc), editable_targets),
            "html.parser",
        )

    section_map = {
        "header": replacement_doc.find("header"),
        "education": replacement_doc.find(id="education"),
        "work_experience": replacement_doc.find(id="work-experience"),
        "projects": replacement_doc.find(id="side-projects"),
        "achievements": replacement_doc.find(id="achievements"),
        "certifications": replacement_doc.find(id="certifications"),
    }
    protected = protect_hard_facts_in_place(
        {key: str(node) if node is not None else "" for key, node in section_map.items()},
        resume,
        language=language,
    )
    for key, old_node in section_map.items():
        corrected = protected.sections.get(key, "")
        corrected_node = BeautifulSoup(corrected, "html.parser").find() if corrected else None
        if old_node is not None and corrected_node is not None:
            old_node.replace_with(corrected_node)

    condensed = str(replacement_doc)
    before_counts = _resume_structure_counts(str(original))
    after_counts = _resume_structure_counts(condensed)
    structure_lost = any(after_counts.get(key, 0) < value for key, value in before_counts.items())
    before_text = len(original.get_text(" ", strip=True))
    after_text = len(replacement_doc.get_text(" ", strip=True))
    completeness_impacted = structure_lost or (before_text > 0 and after_text / before_text < 0.68)
    if structure_lost:
        # Missing entries or bullets are never accepted merely to hit a page target.
        return str(original), True
    return condensed, completeness_impacted


def fit_resume_to_target_pages(
    html_content: str,
    baseline_pdf: bytes,
    target_pages: int,
    *,
    renderer: Any | None = None,
    content_compactor: Callable[[str, float], tuple[str, bool]] | None = None,
    progress_callback: Callable[[int, str, str], None] | None = None,
) -> tuple[str, bytes, int, float, list[str]]:
    """Fit generated content to exactly one or two PDF pages without deleting text."""

    if target_pages not in {1, 2}:
        raise ValueError("target_pages must be 1 or 2")
    baseline_pages = count_pdf_pages(baseline_pdf)
    if progress_callback:
        progress_callback(79, "pdf_page_analysis", f"Baseline PDF has {baseline_pages} page(s)")
    warnings: list[str] = []
    if target_pages == 1 and baseline_pages > 1:
        warnings.append("target_one_page_content_dense")
    elif target_pages == 2 and baseline_pages < 2:
        warnings.append("target_two_pages_content_short")

    owned_driver = None
    if renderer is None:
        from src.utils.chrome_utils import HTML_to_PDF
        from src.utils.chrome_utils import init_browser

        owned_driver = init_browser()

        def renderer(candidate_html: str) -> bytes:
            return base64.b64decode(HTML_to_PDF(candidate_html, owned_driver))

    try:
        best_html = apply_target_page_layout(html_content, 1.0)
        best_pdf = baseline_pdf
        best_pages = baseline_pages
        best_scale = 1.0

        source_html = html_content
        low, high = (0.0, 1.0) if baseline_pages > target_pages else (1.0, 1.35)
        low_html = apply_target_page_layout(source_html, low)
        low_pdf = renderer(low_html)
        low_pages = count_pdf_pages(low_pdf)
        if low_pages <= target_pages:
            best_html, best_pdf, best_pages, best_scale = low_html, low_pdf, low_pages, low
        if progress_callback:
            progress_callback(81, "pdf_layout_fit", f"Minimum spacing rendered: {low_pages} page(s)")

        # Spacing has a deliberately narrow range. If it cannot fit dense
        # content, shorten descriptions with the LLM instead of shrinking text.
        if low_pages > target_pages and content_compactor is not None:
            original_text_length = _resume_visible_text_length(source_html)
            compact_pages = low_pages
            for compaction_round in range(1, 4):
                before_text_length = _resume_visible_text_length(source_html)
                if progress_callback:
                    progress_callback(
                        82,
                        "content_compaction",
                        f"Content round {compaction_round}/3: {compact_pages} page(s) → {target_pages}",
                    )
                try:
                    requested_ratio = max(
                        0.25,
                        min(0.80, (target_pages / compact_pages) * 0.82),
                    )
                    candidate_html, completeness_impacted = content_compactor(
                        source_html, requested_ratio
                    )
                    after_text_length = _resume_visible_text_length(candidate_html)
                    if completeness_impacted:
                        warnings.append("content_completeness_impacted")
                    source_html = candidate_html
                except Exception:
                    logger.exception("Resume content compaction failed; keeping the complete generated copy")
                    warnings.append("content_compaction_failed")
                    break

                compact_html = apply_target_page_layout(source_html, low)
                compact_pdf = renderer(compact_html)
                compact_pages = count_pdf_pages(compact_pdf)
                best_html, best_pdf, best_pages, best_scale = compact_html, compact_pdf, compact_pages, low
                logger.info(
                    "Resume compaction round %s: visible chars %s -> %s, pages=%s, target=%s",
                    compaction_round,
                    before_text_length,
                    after_text_length,
                    compact_pages,
                    target_pages,
                )
                if compact_pages <= target_pages:
                    break
                if after_text_length >= before_text_length * 0.97:
                    warnings.append("content_compaction_insufficient")
                    break

            final_text_length = _resume_visible_text_length(source_html)
            if original_text_length and final_text_length / original_text_length < 0.68:
                warnings.append("content_completeness_impacted")
            high = 1.0

        for pass_index in range(6):
            spacing = (low + high) / 2
            candidate_html = apply_target_page_layout(source_html, spacing)
            candidate_pdf = renderer(candidate_html)
            candidate_pages = count_pdf_pages(candidate_pdf)
            if progress_callback:
                progress_callback(
                    83 + pass_index * 2,
                    "pdf_layout_fit",
                    f"Spacing pass {pass_index + 1}/6: {candidate_pages} page(s), factor {spacing:.3f}",
                )
            if candidate_pages <= target_pages:
                best_html, best_pdf = candidate_html, candidate_pdf
                best_pages, best_scale = candidate_pages, spacing
                low = spacing
            else:
                high = spacing

        if best_pages < target_pages:
            best_html = apply_target_page_layout(source_html, best_scale, stretch_pages=target_pages)
            best_pdf = renderer(best_html)
            best_pages = count_pdf_pages(best_pdf)
            if progress_callback:
                progress_callback(95, "pdf_layout_stretch", f"Expanded sparse content to {target_pages} pages")
        if best_pages != target_pages:
            warnings.append("target_page_fit_limit")
        return best_html, best_pdf, best_pages, round(best_scale, 4), list(dict.fromkeys(warnings))
    finally:
        if owned_driver is not None:
            try:
                owned_driver.quit()
            except Exception:
                pass


_REGENERATABLE_SECTION_IDS = {
    "header", "education", "work-experience", "side-projects", "achievements",
    "academic-achievements", "certifications", "technical-stack", "languages-other", "skills-languages",
}
_REGENERATABLE_ENTRY_SECTION_IDS = {"education", "work-experience", "side-projects"}
_REGENERATION_TARGET = re.compile(r"^(section|entry):([a-z][a-z0-9-]*)(?::(\d+))?$")
_RESUME_SECTION_ORDER = (
    "education", "work-experience", "side-projects", "academic-achievements",
    "achievements", "certifications", "technical-stack", "languages-other", "skills-languages",
)


def validate_regenerate_targets(targets: list[str]) -> list[str]:
    """Normalize and validate client-selected resume modules."""

    normalized = list(dict.fromkeys(target.strip() for target in targets if target.strip()))
    if not normalized:
        raise ValueError("Partial regeneration requires at least one selected module.")
    for target in normalized:
        match = _REGENERATION_TARGET.fullmatch(target)
        if not match:
            raise ValueError(f"Invalid regeneration target: {target}")
        kind, section_id, index = match.groups()
        if section_id not in _REGENERATABLE_SECTION_IDS:
            raise ValueError(f"Unsupported resume section: {section_id}")
        if kind == "section" and index is not None:
            raise ValueError(f"Section target cannot include an entry index: {target}")
        if kind == "entry":
            if section_id not in _REGENERATABLE_ENTRY_SECTION_IDS or index is None:
                raise ValueError(f"Unsupported resume entry target: {target}")
    return normalized


def merge_regenerated_resume_html(base_html: str, generated_html: str, targets: list[str]) -> str:
    """Replace only selected modules while preserving every unselected base node."""

    from bs4 import BeautifulSoup

    if not base_html.strip():
        raise ValueError("Partial regeneration requires a base resume version.")
    normalized_targets = validate_regenerate_targets(targets)
    base_soup = BeautifulSoup(_sanitize_edited_resume_html(base_html), "html.parser")
    generated_soup = BeautifulSoup(generated_html, "html.parser")

    section_targets = {
        target.split(":", 1)[1]
        for target in normalized_targets
        if target.startswith("section:")
    }
    for section_id in section_targets:
        old_node = base_soup.find("header") if section_id == "header" else base_soup.find(id=section_id)
        new_node = generated_soup.find("header") if section_id == "header" else generated_soup.find(id=section_id)
        if new_node is None:
            raise ValueError(f"Generated resume is missing selected section: {section_id}")
        replacement = new_node.extract()
        if old_node is not None:
            old_node.replace_with(replacement)
        elif base_soup.body is not None:
            container = base_soup.body.find("main") or base_soup.body
            section_index = _RESUME_SECTION_ORDER.index(section_id)
            next_node = next(
                (
                    container.find(id=candidate, recursive=False)
                    for candidate in _RESUME_SECTION_ORDER[section_index + 1:]
                    if container.find(id=candidate, recursive=False) is not None
                ),
                None,
            )
            if next_node is not None:
                next_node.insert_before(replacement)
            else:
                container.append(replacement)
        else:
            raise ValueError("Base resume HTML has no body for inserting selected section.")

    for target in normalized_targets:
        if not target.startswith("entry:"):
            continue
        _, section_id, raw_index = target.split(":", 2)
        if section_id in section_targets:
            continue
        index = int(raw_index)
        old_section = base_soup.find(id=section_id)
        new_section = generated_soup.find(id=section_id)
        if old_section is None or new_section is None:
            raise ValueError(f"Resume is missing selected entry section: {section_id}")
        old_entries = list(old_section.select(".entry"))
        new_entries = list(new_section.select(".entry"))
        if index >= len(old_entries) or index >= len(new_entries):
            raise ValueError(f"Selected resume entry no longer exists: {target}")
        old_entries[index].replace_with(new_entries[index].extract())

    return str(base_soup)


def build_preserved_resume_context(base_html: str, targets: list[str], max_chars: int = 40_000) -> str:
    """Build LLM context from locked content plus the current HTML format."""

    from bs4 import BeautifulSoup

    normalized_targets = validate_regenerate_targets(targets)
    soup = BeautifulSoup(_sanitize_edited_resume_html(base_html), "html.parser")
    for unsafe in soup.select("script, iframe, object, embed"):
        unsafe.decompose()

    style_reference = "\n".join(str(style) for style in soup.select("head style"))
    section_targets = {
        target.split(":", 1)[1]
        for target in normalized_targets
        if target.startswith("section:")
    }
    for section_id in section_targets:
        node = soup.find("header") if section_id == "header" else soup.find(id=section_id)
        if node is not None:
            node.decompose()
    for target in normalized_targets:
        if not target.startswith("entry:"):
            continue
        _, section_id, raw_index = target.split(":", 2)
        if section_id in section_targets:
            continue
        section = soup.find(id=section_id)
        entries = list(section.select(".entry")) if section is not None else []
        index = int(raw_index)
        if index < len(entries):
            entries[index].decompose()

    body_reference = str(soup.body) if soup.body is not None else str(soup)
    # Keep both parts represented even when a template carries a very large stylesheet.
    # Formatting is useful context, but locked facts must never be crowded out by CSS.
    wrapper_allowance = 180
    available_chars = max(0, max_chars - wrapper_allowance)
    style_budget = min(12_000, available_chars // 3)
    style_reference = style_reference[:style_budget]
    body_budget = max(0, available_chars - len(style_reference))
    body_reference = body_reference[:body_budget]
    context = (
        "<PRESERVED_RESUME_CONTEXT>\n"
        "<FORMAT_REFERENCE>\n"
        f"{style_reference}\n"
        "</FORMAT_REFERENCE>\n"
        "<LOCKED_CONTENT>\n"
        f"{body_reference}\n"
        "</LOCKED_CONTENT>\n"
        "</PRESERVED_RESUME_CONTEXT>"
    )
    return context[:max_chars]


def convert_html_to_pdf(
    html_content: str,
    filename_base: str = "edited",
    *,
    overwrite_pdf_filename: str = "",
    overwrite_html_filename: str = "",
) -> dict[str, Any]:
    """Convert an arbitrary full HTML document to PDF and save it.

    Used by the WYSIWYG editor's "Save" feature: the user edits the
    rendered HTML in the iframe and clicks Save — we render that
    HTML directly to PDF (no LLM call) and persist both PDF and HTML
    so the new version appears in history.

    Args:
        html_content: Full HTML document string (with <html>/<head>/<body>).
        filename_base: Prefix for the output filename.

    Returns:
        {"status", "pdf_filename", "html_filename", "pdf_size"}.
    """
    if not html_content or not html_content.strip():
        raise ValueError("HTML content cannot be empty")

    # Defense in depth: editor-only DOM attributes and highlight CSS must
    # never be persisted or rendered, even when an older frontend submits
    # unsanitized iframe HTML.
    html_content = _sanitize_edited_resume_html(html_content)

    from backend.services.config_service import PUBLIC_DEMO_MODE
    if overwrite_pdf_filename and overwrite_html_filename and not PUBLIC_DEMO_MODE:
        pdf_filename = Path(overwrite_pdf_filename).name
        html_filename = Path(overwrite_html_filename).name
        if not pdf_filename.lower().endswith(".pdf") or not html_filename.lower().endswith(".html"):
            raise ValueError("Overwrite targets must be a PDF/HTML pair")
    elif PUBLIC_DEMO_MODE:
        cleanup_public_artifacts()
        token = uuid.uuid4().hex
        pdf_filename = f"public_{token}.pdf"
        html_filename = f"public_{token}.html"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_base = re.sub(r"[^\w\-.\u4e00-\u9fff]+", "_", filename_base, flags=re.UNICODE).strip("._")
        safe_base = safe_base[:80] or "resume_edited"
        pdf_filename = f"{safe_base}_{timestamp}.pdf"
        html_filename = f"{safe_base}_{timestamp}.html"

    pdf_path = OUTPUT_FOLDER / pdf_filename
    html_path = OUTPUT_FOLDER / html_filename

    # Write the HTML file (so user can re-preview later)
    html_path.write_text(html_content, encoding="utf-8")

    # Render through the same function used by the WYSIWYG PDF preview.
    pdf_bytes = render_html_to_pdf_bytes(html_content)
    pdf_path.write_bytes(pdf_bytes)

    return {
        "status": "success",
        "pdf_filename": pdf_filename,
        "html_filename": html_filename,
        "pdf_path": str(pdf_path),
        "html_path": str(html_path),
        "pdf_size": len(pdf_bytes),
    }


def rename_saved_resume(pdf_filename: str, html_filename: str, new_name: str) -> dict[str, str]:
    """Rename an existing saved PDF/HTML pair without leaving an orphan file."""
    source_pdf = OUTPUT_FOLDER / Path(pdf_filename).name
    source_html = OUTPUT_FOLDER / Path(html_filename).name
    if not source_pdf.is_file() or not source_html.is_file():
        raise FileNotFoundError("Current resume PDF/HTML pair was not found")
    safe_name = re.sub(r"[^\w\-.\u4e00-\u9fff]+", "_", new_name, flags=re.UNICODE).strip("._")[:80]
    if not safe_name:
        raise ValueError("Resume name cannot be empty")
    target_pdf = OUTPUT_FOLDER / f"{safe_name}.pdf"
    target_html = OUTPUT_FOLDER / f"{safe_name}.html"
    if (target_pdf.exists() and target_pdf != source_pdf) or (target_html.exists() and target_html != source_html):
        raise FileExistsError(f'A resume named "{safe_name}" already exists')
    source_pdf.replace(target_pdf)
    try:
        source_html.replace(target_html)
    except Exception:
        target_pdf.replace(source_pdf)
        raise
    return {"pdf_filename": target_pdf.name, "html_filename": target_html.name}


# ---------------------------------------------------------------------------
# AI 智能改写助手（Roadmap §1）
# ---------------------------------------------------------------------------

_REWRITE_SYSTEM_PROMPTS = {
    "zh": {
        "more_quantified": (
            "你是一个专业的简历润色专家，擅长把模糊的描述改写为有数据支撑的表达。\n"
            "请将用户提供的文本改写为：\n"
            "1. 只能保留原文已经出现的数字、百分比、时间和规模，严禁补造任何数值\n"
            "2. 使用动词开头的 STAR 风格描述（情境、任务、行动、结果）\n"
            "3. 原文没有量化数据时，只优化表达，不得用示例数字或占位数字代替\n"
            "4. 保持原意不变，只是更量化\n"
            "5. 如果原文中确实无法量化（如性格描述），保持原文\n\n"
            "只输出改写后的文本，不要任何解释、前缀或 markdown 代码块标记。"
        ),
        "more_professional": (
            "你是一个专业的简历润色专家，擅长使用行业术语提升专业感。\n"
            "请将用户提供的文本改写为：\n"
            "1. 使用该行业的专业术语和标准表达\n"
            "2. 替换口语化、随意的措辞\n"
            "3. 使用更正式的商业/技术词汇\n"
            "4. 保持原意不变，只是更专业\n\n"
            "只输出改写后的文本，不要任何解释、前缀或 markdown 代码块标记。"
        ),
        "more_concise": (
            "你是一个专业的简历润色专家，擅长把冗长的描述压缩为简洁有力的表达。\n"
            "请将用户提供的文本改写为：\n"
            "1. 删除冗余词汇和重复信息\n"
            "2. 把多个短句合并为一个有力长句\n"
            "3. 删除『负责…』、『参与…』等弱动词开头的废话\n"
            "4. 保留所有关键信息，但字数减少 30-50%\n\n"
            "只输出改写后的文本，不要任何解释、前缀或 markdown 代码块标记。"
        ),
        "fix_grammar": (
            "你是一个专业的简历校对专家，擅长修正中文/英文文本的语法错误。\n"
            "请修正用户提供的文本中的：\n"
            "1. 拼写错误（包括中英文）\n"
            "2. 语法错误\n"
            "3. 标点符号错误（中文用全角，英文用半角）\n"
            "4. 中英文混排时的空格问题\n"
            "5. 错别字\n\n"
            "只输出修正后的文本，不要任何解释、前缀或 markdown 代码块标记。"
        ),
    },
    "en": {
        "more_quantified": (
            "You are a professional resume editor specializing in transforming "
            "vague descriptions into quantified achievements.\n"
            "Rewrite the user's text to:\n"
            "1. Preserve only numbers, percentages, timeframes, and scale already present in the source; never invent metrics\n"
            "2. Use action-verb-led STAR phrasing (Situation, Task, Action, Result)\n"
            "3. If the source has no metrics, improve wording without adding example or placeholder numbers\n"
            "4. Preserve original meaning — only make it more measurable\n"
            "5. If something cannot be quantified (e.g. soft skills), keep the original\n\n"
            "Output ONLY the rewritten text. No explanations, no prefixes, no markdown fences."
        ),
        "more_professional": (
            "You are a professional resume editor specializing in elevating "
            "professional tone.\n"
            "Rewrite the user's text to:\n"
            "1. Use industry-standard terminology\n"
            "2. Replace casual or generic phrasing\n"
            "3. Adopt formal business / technical vocabulary\n"
            "4. Preserve original meaning — only make it more polished\n\n"
            "Output ONLY the rewritten text. No explanations, no prefixes, no markdown fences."
        ),
        "more_concise": (
            "You are a professional resume editor specializing in concise writing.\n"
            "Rewrite the user's text to:\n"
            "1. Remove redundant words and repeated information\n"
            "2. Merge short sentences into tight, punchy ones\n"
            "3. Cut filler phrases like \"responsible for\", \"worked on\"\n"
            "4. Keep all key information but reduce length by 30-50%\n\n"
            "Output ONLY the rewritten text. No explanations, no prefixes, no markdown fences."
        ),
        "fix_grammar": (
            "You are a professional proofreader.\n"
            "Correct the user's text for:\n"
            "1. Spelling errors\n"
            "2. Grammar mistakes\n"
            "3. Punctuation issues\n"
            "4. Inconsistent capitalization\n"
            "5. Awkward phrasing\n\n"
            "Output ONLY the corrected text. No explanations, no prefixes, no markdown fences."
        ),
    },
}


def rewrite_text(
    text: str,
    mode: str,
    context: str = "",
    target_language: str = "zh",
    api_key: str = "",
    model_type: str = "anthropic",
    model_name: str = "",
    base_url: str = "https://api.minimaxi.com/anthropic",
    llm_protocol: str = "",
) -> str:
    """AI 智能改写助手 — rewrite selected text using LLM.

    Args:
        text: The selected text to rewrite.
        mode: One of "more_quantified" | "more_professional" |
              "more_concise" | "fix_grammar".
        context: Optional surrounding text to give the LLM context.
        target_language: Output language ("zh" or "en").
        api_key, model_type, base_url, llm_protocol: Standard LLM
            credentials (3-level fallback applied for api_key).

    Returns:
        The rewritten text. Plain text, no markdown fences.

    Strategy:
        - Resolve API key via fallback chain (param → secrets → config).
        - Normalize the provider endpoint without mutating global model config.
        - Execute the versioned text_rewriter Skill through AIRuntime.
    """
    secrets = load_secrets()
    from backend.services.config_service import PUBLIC_DEMO_MODE
    if PUBLIC_DEMO_MODE and (not api_key or api_key.startswith("sk-your-")):
        raise ValueError("Public demo requires your own API key for each AI request.")

    # ---- 3-level API key fallback ----
    if not api_key or api_key.startswith("sk-your-"):
        secrets = load_secrets()
        secrets_key = secrets.get("llm_api_key", "")
        if secrets_key and not secrets_key.startswith("sk-your-"):
            api_key = secrets_key
    if not api_key or api_key.startswith("sk-your-"):
        import config as root_config
        config_key = getattr(root_config, "ANTHROPIC_AUTH_TOKEN", "")
        if config_key and not config_key.startswith("sk-your-"):
            api_key = config_key
    if not api_key or api_key.startswith("sk-your-"):
        raise ValueError(
            "未配置有效的 API Key。请在「设置」页面配置 API Key。"
        )

    # ---- Apply config so downstream code uses the right key/URL/protocol ----
    # Strip any path/query from base_url — langchain ChatOpenAI appends
    # "/chat/completions" (or "/responses") automatically, so a full URL
    # like "https://api.minimaxi.com/anthropic/v1/messages" would
    # produce a 404 (".../v1/messages/chat/completions").
    from src.libs.resume_and_cover_builder.llm.llm_generate_resume import _strip_base_url_path

    normalized_base_url = _strip_base_url_path(
        base_url, proto=llm_protocol or ("anthropic" if model_type == "anthropic" else "openai_chat")
    ) if base_url else ""

    if not model_name:
        from backend.services.config_service import resolve_llm_model
        model_name = resolve_llm_model(model_type, saved_model=secrets.get("llm_model", ""), saved_provider=secrets.get("llm_model_provider", ""))

    # ---- Execute through the unified AI Runtime ----
    from backend.services.ai_runtime_service import build_ai_runtime
    from src.libs.ai_engine.skills.builtin import TextRewriterSkill

    provider = model_type or ("anthropic" if llm_protocol == "anthropic" else "openai")
    bundle = build_ai_runtime({
        "api_key": api_key,
        "base_url": normalized_base_url,
        "provider": provider,
        "model": model_name,
    }, [TextRewriterSkill(_REWRITE_SYSTEM_PROMPTS)])
    result = bundle.runtime.execute(
        "text_rewriter",
        {
            "text": text,
            "mode": mode,
            "context": context,
            "target_language": target_language,
        },
        provider=provider,
        model=model_name,
    )
    rewritten = result.content.strip()

    if not rewritten:
        # Defensive: if LLM returned empty, return the original
        return text

    from src.libs.ai_engine.harness import validate_grounded_text
    violations = validate_grounded_text(text, rewritten)
    if violations:
        logger.warning("Resume rewrite fact harness rejected output: %s", violations)
        return text

    return rewritten


def generate_resume(
    api_key: str,
    model_type: str,
    base_url: str,
    style_name: str,
    job_description: str | None,
    resume_language: str = "zh",
    system_language: str = "zh",
    llm_protocol: str | None = None,
    model_name: str = "",
    resume_content: str = "",
    generation_mode: str = "new",
    base_html: str = "",
    regenerate_targets: list[str] | None = None,
    target_pages: int = 1,
    request_id: str = "",
) -> dict[str, Any]:
    """Generate a resume PDF. Returns {path, filename, status}."""
    report = lambda progress, stage, detail="": update_generation_progress(
        request_id, progress, stage, detail
    )
    report(2, "request_validation", "Validating generation options")
    from src.libs.resume_and_cover_builder import ResumeFacade, ResumeGenerator, StyleManager
    from src.resume_schemas.resume import Resume
    from src.utils.chrome_utils import init_browser
    import src.libs.resume_and_cover_builder.config as rcb_config
    import config as root_config


    from backend.services.config_service import PUBLIC_DEMO_MODE
    if target_pages not in {1, 2}:
        raise ValueError("target_pages must be 1 or 2")
    if generation_mode not in {"new", "partial"}:
        raise ValueError(f"Unsupported generation mode: {generation_mode}")
    selected_targets = (
        validate_regenerate_targets(regenerate_targets or [])
        if generation_mode == "partial"
        else []
    )
    if generation_mode == "partial" and not base_html.strip():
        raise ValueError("Partial regeneration requires the current resume version.")
    preserved_context = (
        build_preserved_resume_context(base_html, selected_targets)
        if generation_mode == "partial"
        else ""
    )
    report(6, "generation_mode", f"Mode={generation_mode}, target={target_pages} page(s)")
    if PUBLIC_DEMO_MODE and (not api_key or api_key.startswith("sk-your-")):
        raise ValueError("Public demo requires your own API key for each AI request.")

    # Local installs persist configuration; public demo credentials must never be saved.
    if api_key and not PUBLIC_DEMO_MODE:
        save_secrets({
            "llm_api_key": api_key,
            "llm_model_type": model_type,
            "llm_model": model_name,
            "llm_model_provider": model_type,
            "llm_base_url": base_url,
            "llm_protocol": llm_protocol or "",
            "resume_language": resume_language,
            "system_language": system_language,
        })

    # Fallback chain: explicit param → secrets.yaml → config.py
    if not api_key or api_key.startswith("sk-your-"):
        secrets = load_secrets()
        secrets_key = secrets.get("llm_api_key", "")
        if secrets_key and not secrets_key.startswith("sk-your-"):
            api_key = secrets_key
            logger.info("Loaded api_key from secrets.yaml")

    if not api_key or api_key.startswith("sk-your-"):
        # Last resort: try config.py
        import config as root_config
        config_key = getattr(root_config, "ANTHROPIC_AUTH_TOKEN", "")
        if config_key and not config_key.startswith("sk-your-"):
            api_key = config_key
            logger.info("Loaded api_key from config.py")

    if not model_type or model_type == "anthropic":
        if not model_type:
            secrets = load_secrets()
            model_type = secrets.get("llm_model_type", "anthropic")
    if not base_url:
        secrets = load_secrets()
        base_url = secrets.get("llm_base_url", "") or "https://api.minimaxi.com/anthropic"
    if not model_name:
        secrets = load_secrets()
        from backend.services.config_service import resolve_llm_model
        model_name = resolve_llm_model(model_type, saved_model=secrets.get("llm_model", ""), saved_provider=secrets.get("llm_model_provider", ""))

    # Resolve LLM protocol with fallback chain (param → secrets → config)
    if not llm_protocol:
        secrets = load_secrets()
        llm_protocol = secrets.get("llm_protocol", "")
    if not llm_protocol:
        llm_protocol = getattr(root_config, "LLM_PROTOCOL", "anthropic")
    if llm_protocol not in ("anthropic", "openai_chat", "openai_response"):
        llm_protocol = "anthropic"  # safe default

    # Update the global config so downstream code uses the right key
    if api_key:
        rcb_config.API_KEY = api_key
        root_config.ANTHROPIC_AUTH_TOKEN = api_key
    if base_url:
        rcb_config.LLM_API_URL = base_url
        root_config.LLM_API_URL = base_url
        root_config.ANTHROPIC_BASE_URL = base_url
        # Also set anthropic-specific config
        try:
            rcb_config.ANTHROPIC_AUTH_TOKEN = api_key
            rcb_config.ANTHROPIC_BASE_URL = base_url
        except AttributeError:
            pass
    if model_type:
        rcb_config.LLM_MODEL_TYPE = model_type
        root_config.LLM_MODEL_TYPE = model_type
    if model_name:
        rcb_config.LLM_MODEL = model_name
        root_config.LLM_MODEL = model_name
        root_config.ANTHROPIC_MODEL = model_name
        root_config.OPENAI_MODEL = model_name
    # Apply the resolved protocol so _resolve_protocol() returns it
    try:
        rcb_config.LLM_PROTOCOL = llm_protocol
    except AttributeError:
        pass
    root_config.LLM_PROTOCOL = llm_protocol
    report(10, "llm_configuration", "Resolved model provider and credentials")

    if not api_key or api_key.startswith("sk-your-"):
        raise ValueError(
            "未配置有效的 API Key。请在「设置」页面或主页面配置 API Key。"
        )

    # Load resume content
    if resume_content.strip():
        plain_text_resume = resume_content
    elif PUBLIC_DEMO_MODE:
        raise ValueError("Public demo requires the current browser resume content.")
    else:
        resume_file = DATA_FOLDER / ("plain_text_resume.yaml" if resume_language == "en" else "plain_text_resume_zh.yaml")
        with open(resume_file, "r", encoding="utf-8") as f:
            plain_text_resume = f.read()
    report(15, "resume_loading", "Loaded source resume content")
    from backend.services.resume_validation import validate_resume_yaml
    validation = validate_resume_yaml(plain_text_resume)
    if not validation["valid"]:
        missing = "；".join(
            f'{item["path"]}: {item["message"]}' for item in validation["errors"]
        )
        raise ValueError(f"简历关键字段未填写完整，无法生成：{missing}")

    report(20, "resume_validation", "Resume schema and required facts validated")

    # Setup style
    style_manager = StyleManager()
    available_styles = style_manager.get_styles()
    if style_name and style_name in available_styles:
        style_manager.set_selected_style(style_name)
    elif available_styles:
        style_manager.set_selected_style(list(available_styles.keys())[0])
    report(24, "style_selection", f"Selected resume style: {style_name or 'default'}")

    # Generate
    resume_generator = ResumeGenerator()
    resume_generator.set_regeneration_context(preserved_context, selected_targets)
    resume_generator.set_target_pages(target_pages)
    resume_generator.set_progress_callback(report)
    resume_object = Resume(plain_text_resume)
    driver = init_browser()
    resume_generator.set_resume_object(resume_object)

    resume_facade = ResumeFacade(
        api_key=api_key,
        style_manager=style_manager,
        resume_generator=resume_generator,
        resume_object=resume_object,
        output_path=OUTPUT_FOLDER,
        resume_language=resume_language,
        system_language=system_language,
    )
    resume_facade.set_driver(driver)
    resume_facade.set_progress_callback(report)

    try:
        is_tailored = job_description and job_description.strip()
        if is_tailored:
            report(27, "job_tailoring", "Preparing job-tailored generation")
            style_path = style_manager.get_style_path()
            # Pass JD text directly — avoids the need to pre-populate self.job
            # via link_to_job() which would require URL scraping.
            result, suggested_name, html_b64 = resume_facade.create_resume_pdf_job_tailored(
                job_description_text=job_description,
            )
            pdf_data = base64.b64decode(result)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"resume_tailored_{timestamp}_{suggested_name}.pdf"
        else:
            report(27, "base_generation", "Preparing resume generation")
            result, html_b64 = resume_facade.create_resume_pdf()
            pdf_data = base64.b64decode(result)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"resume_{timestamp}.pdf"

        generated_html = base64.b64decode(html_b64).decode("utf-8")
        report(77, "baseline_pdf_ready", "Generated baseline HTML and PDF")
        if generation_mode == "partial":
            final_html = merge_regenerated_resume_html(base_html, generated_html, selected_targets)
            pdf_data = render_html_to_pdf_bytes(final_html)
            filename = filename.replace("resume_", "resume_partial_", 1)
            report(78, "partial_merge", "Merged regenerated modules with retained content")
        else:
            final_html = generated_html

        def compact_for_layout(candidate_html: str, target_text_ratio: float) -> tuple[str, bool]:
            return condense_resume_html_with_llm(
                candidate_html,
                resume_object,
                api_key,
                language=resume_language,
                target_pages=target_pages,
                editable_targets=selected_targets if generation_mode == "partial" else None,
                target_text_ratio=target_text_ratio,
            )

        final_html, pdf_data, actual_pages, layout_scale, layout_warnings = fit_resume_to_target_pages(
            final_html,
            pdf_data,
            target_pages,
            content_compactor=compact_for_layout,
            progress_callback=report,
        )

        if PUBLIC_DEMO_MODE:
            cleanup_public_artifacts()
            filename = f"public_{uuid.uuid4().hex}.pdf"
        output_path = OUTPUT_FOLDER / filename
        with open(output_path, "wb") as f:
            f.write(pdf_data)
        report(97, "file_save", "Saved final PDF")

        if not PUBLIC_DEMO_MODE:
            with open(OUTPUT_FOLDER / "resume_base.pdf", "wb") as f:
                f.write(pdf_data)

        # Save HTML alongside the PDF for later preview
        html_filename = filename.replace(".pdf", ".html")
        html_path = OUTPUT_FOLDER / html_filename
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(final_html)
        report(99, "html_save", "Saved editable HTML version")

        response = {
            "path": str(output_path),
            "filename": filename,
            "html_filename": html_filename,
            "html_path": str(html_path),
            "status": "success",
            "generation_mode": generation_mode,
            "regenerated_targets": selected_targets,
            "target_pages": target_pages,
            "actual_pages": actual_pages,
            "layout_warnings": layout_warnings,
            "layout_scale": layout_scale,
            "request_id": request_id,
        }
        update_generation_progress(request_id, 100, "completed", "Resume generation completed", status="completed")
        return response
    finally:
        try:
            driver.quit()
        except Exception:
            pass
