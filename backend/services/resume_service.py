"""Resume generation service — wraps existing src/ logic."""

from __future__ import annotations

import base64
import html as html_lib
import logging
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any

import yaml

from backend.services.config_service import load_secrets, save_secrets

logger = logging.getLogger(__name__)

DATA_FOLDER = Path("data_folder")
OUTPUT_FOLDER = DATA_FOLDER / "output"
STYLES_DIR = Path("src/libs/resume_and_cover_builder/resume_style")

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)


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


def _render_resume_preview_body(data: dict[str, Any]) -> str:
    """Render the resume YAML data into a simple HTML body for preview.

    This deliberately avoids invoking the LLM so the preview can be
    generated in milliseconds. The visual style is governed by the
    selected CSS template, the body content is rendered from the local
    YAML resume.
    """
    parts: list[str] = []

    personal = data.get("personal_information") or {}
    if personal:
        name = _escape(personal.get("name") or "")
        surname = _escape(personal.get("surname") or "")
        full_name = f"{name} {surname}".strip()
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
    summary = data.get("summary") or data.get("objective")
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
            items.append(
                f'<div class="preview-item">'
                f'<div class="preview-item-head">'
                f'<span class="preview-item-title">{_escape(edu.get("institution") or "")}</span>'
                f'<span class="preview-item-period">'
                f'{_escape(edu.get("start_date") or "")} &ndash; {_escape(edu.get("year_of_completion") or "")}'
                f'</span></div>'
                f'<div class="preview-item-sub">{_escape(edu.get("education_level") or "")} '
                f'&middot; {_escape(edu.get("field_of_study") or "")}</div>'
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

    body_html = _render_resume_preview_body(data)
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


def generate_resume(
    api_key: str,
    model_type: str,
    base_url: str,
    style_name: str,
    job_description: str | None,
    resume_language: str = "zh",
    system_language: str = "zh",
) -> dict[str, Any]:
    """Generate a resume PDF. Returns {path, filename, status}."""
    from src.libs.resume_and_cover_builder import ResumeFacade, ResumeGenerator, StyleManager
    from src.resume_schemas.resume import Resume
    from src.utils.chrome_utils import init_browser
    import src.libs.resume_and_cover_builder.config as rcb_config

    # Save config first (so subsequent runs have it)
    if api_key:
        save_secrets({
            "llm_api_key": api_key,
            "llm_model_type": model_type,
            "llm_base_url": base_url,
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

    # Update the global config so downstream code uses the right key
    if api_key:
        rcb_config.API_KEY = api_key
    if base_url:
        rcb_config.LLM_API_URL = base_url
        # Also set anthropic-specific config
        try:
            rcb_config.ANTHROPIC_AUTH_TOKEN = api_key
            rcb_config.ANTHROPIC_BASE_URL = base_url
        except AttributeError:
            pass
    if model_type:
        rcb_config.LLM_MODEL_TYPE = model_type

    if not api_key or api_key.startswith("sk-your-"):
        raise ValueError(
            "未配置有效的 API Key。请在「设置」页面或主页面配置 API Key。"
        )

    # Load resume content
    resume_file = DATA_FOLDER / ("plain_text_resume.yaml" if resume_language == "en" else "plain_text_resume_zh.yaml")
    with open(resume_file, "r", encoding="utf-8") as f:
        plain_text_resume = f.read()

    # Setup style
    style_manager = StyleManager()
    available_styles = style_manager.get_styles()
    if style_name and style_name in available_styles:
        style_manager.set_selected_style(style_name)
    elif available_styles:
        style_manager.set_selected_style(list(available_styles.keys())[0])

    # Generate
    resume_generator = ResumeGenerator()
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

    try:
        is_tailored = job_description and job_description.strip()
        if is_tailored:
            style_path = style_manager.get_style_path()
            result, suggested_name, html_b64 = resume_facade.create_resume_pdf_job_tailored()
            pdf_data = base64.b64decode(result)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"resume_tailored_{timestamp}_{suggested_name}.pdf"
        else:
            result, html_b64 = resume_facade.create_resume_pdf()
            pdf_data = base64.b64decode(result)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"resume_{timestamp}.pdf"

        output_path = OUTPUT_FOLDER / filename
        with open(output_path, "wb") as f:
            f.write(pdf_data)

        # Also save as resume_base.pdf
        with open(OUTPUT_FOLDER / "resume_base.pdf", "wb") as f:
            f.write(pdf_data)

        # Save HTML alongside the PDF for later preview
        html_filename = filename.replace(".pdf", ".html")
        html_path = OUTPUT_FOLDER / html_filename
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(base64.b64decode(html_b64).decode("utf-8"))

        return {
            "path": str(output_path),
            "filename": filename,
            "html_filename": html_filename,
            "html_path": str(html_path),
            "status": "success",
        }
    finally:
        try:
            driver.quit()
        except Exception:
            pass
