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


def convert_html_to_pdf(
    html_content: str,
    filename_base: str = "edited",
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
    import base64 as _b64
    from src.utils.chrome_utils import HTML_to_PDF, init_browser

    if not html_content or not html_content.strip():
        raise ValueError("HTML content cannot be empty")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"{filename_base}_{timestamp}.pdf"
    html_filename = f"{filename_base}_{timestamp}.html"

    pdf_path = OUTPUT_FOLDER / pdf_filename
    html_path = OUTPUT_FOLDER / html_filename

    # Write the HTML file (so user can re-preview later)
    html_path.write_text(html_content, encoding="utf-8")

    # Render to PDF using Chrome headless
    driver = init_browser()
    try:
        pdf_b64 = HTML_to_PDF(html_content, driver)
        pdf_bytes = _b64.b64decode(pdf_b64)
        pdf_path.write_bytes(pdf_bytes)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return {
        "status": "success",
        "pdf_filename": pdf_filename,
        "html_filename": html_filename,
        "pdf_path": str(pdf_path),
        "html_path": str(html_path),
        "pdf_size": len(pdf_bytes),
    }


# ---------------------------------------------------------------------------
# AI 智能改写助手（Roadmap §1）
# ---------------------------------------------------------------------------

_REWRITE_SYSTEM_PROMPTS = {
    "zh": {
        "more_quantified": (
            "你是一个专业的简历润色专家，擅长把模糊的描述改写为有数据支撑的表达。\n"
            "请将用户提供的文本改写为：\n"
            "1. 增加具体的数字、百分比、时间、规模等量化指标\n"
            "2. 使用动词开头的 STAR 风格描述（情境、任务、行动、结果）\n"
            "3. 强调可衡量的成果（如性能提升 X%、节省 X 小时、用户量 X 万等）\n"
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
            "1. Add concrete numbers, percentages, timeframes, and scale metrics\n"
            "2. Use action-verb-led STAR phrasing (Situation, Task, Action, Result)\n"
            "3. Emphasize measurable outcomes (e.g. \"improved X by Y%\", "
            "\"served X users\", \"reduced X by Y hours\")\n"
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
        - Set rcb_config globals so the existing LLM infra picks them up.
        - Build a focused single-turn prompt and call the chat model
          directly (returns AIMessage; we extract its text content).
    """
    from src.libs.resume_and_cover_builder.llm.llm_generate_resume import (
        _create_chat_model,
    )
    from src.libs.resume_and_cover_builder.llm.llm_generate_resume import (
        ContentBlockParser,
    )
    from langchain_core.messages import HumanMessage
    import src.libs.resume_and_cover_builder.config as rcb_config
    import config as root_config

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
    from urllib.parse import urlparse, urlunparse

    def _strip_path(u: str) -> str:
        if not u:
            return u
        try:
            p = urlparse(u)
            return urlunparse((p.scheme, p.netloc, "", "", "", ""))
        except Exception:
            return u

    normalized_base_url = _strip_path(base_url) if base_url else ""

    rcb_config.API_KEY = api_key
    root_config.ANTHROPIC_AUTH_TOKEN = api_key
    if normalized_base_url:
        rcb_config.LLM_API_URL = normalized_base_url
        root_config.LLM_API_URL = normalized_base_url
        root_config.ANTHROPIC_BASE_URL = normalized_base_url
        try:
            rcb_config.ANTHROPIC_AUTH_TOKEN = api_key
            rcb_config.ANTHROPIC_BASE_URL = normalized_base_url
        except AttributeError:
            pass
    if model_type:
        rcb_config.LLM_MODEL_TYPE = model_type
        root_config.LLM_MODEL_TYPE = model_type
    if llm_protocol:
        try:
            rcb_config.LLM_PROTOCOL = llm_protocol
        except AttributeError:
            pass
        root_config.LLM_PROTOCOL = llm_protocol

    # ---- Build prompt ----
    lang = "en" if target_language == "en" else "zh"
    system_prompt = _REWRITE_SYSTEM_PROMPTS.get(lang, _REWRITE_SYSTEM_PROMPTS["zh"]).get(mode)
    if system_prompt is None:
        raise ValueError(f"Unsupported rewrite mode: {mode}")

    # Use string.Template to avoid .format() choking on { } in the user's text
    from string import Template
    if context:
        user_prompt_template = Template(
            "【上下文（仅供参考，无需修改）】\n$context\n\n"
            "【需要改写的文本】\n$text\n"
        )
        user_prompt = user_prompt_template.substitute(context=context, text=text)
    else:
        user_prompt_template = Template("【需要改写的文本】\n$text\n")
        user_prompt = user_prompt_template.substitute(text=text)

    # ---- Call LLM directly (no LoggerChatModel — it's designed for chains) ----
    client = _create_chat_model(api_key)
    response = client.invoke([
        {"role": "system", "content": system_prompt},
        HumanMessage(content=user_prompt),
    ])

    # Extract content (string or list of content blocks)
    content = getattr(response, "content", response)
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        content = "".join(parts)

    rewritten = (str(content) if content else "").strip()

    # Strip any leading/trailing markdown fences the LLM might add
    import re as _re
    rewritten = _re.sub(r"^```[a-zA-Z]*\s*", "", rewritten)
    rewritten = _re.sub(r"\s*```\s*$", "", rewritten)

    if not rewritten:
        # Defensive: if LLM returned empty, return the original
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
) -> dict[str, Any]:
    """Generate a resume PDF. Returns {path, filename, status}."""
    from src.libs.resume_and_cover_builder import ResumeFacade, ResumeGenerator, StyleManager
    from src.resume_schemas.resume import Resume
    from src.utils.chrome_utils import init_browser
    import src.libs.resume_and_cover_builder.config as rcb_config
    import config as root_config

    # Save config first (so subsequent runs have it)
    if api_key:
        save_secrets({
            "llm_api_key": api_key,
            "llm_model_type": model_type,
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
    # Apply the resolved protocol so _resolve_protocol() returns it
    try:
        rcb_config.LLM_PROTOCOL = llm_protocol
    except AttributeError:
        pass
    root_config.LLM_PROTOCOL = llm_protocol

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
            # Pass JD text directly — avoids the need to pre-populate self.job
            # via link_to_job() which would require URL scraping.
            result, suggested_name, html_b64 = resume_facade.create_resume_pdf_job_tailored(
                job_description_text=job_description,
            )
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
