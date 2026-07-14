"""Document parser — extracts structured resume data from various file formats.

Two-tier strategy:
  1. YAML / JSON files  →  yaml.safe_load  (perfect accuracy, zero LLM cost)
  2. All other formats   →  extract plain text  →  LLM structured extraction

The LLM approach far outperforms heuristic regex mapping because resumes come
in countless layouts; the model understands context and field semantics.

API credentials are read from global_config (already set by the caller via
the resume_service 3-level fallback: request param → secrets.yaml → config.py).
"""

from __future__ import annotations

import io
import os
import re
from urllib.parse import urlparse, urlunparse
from typing import Any

import yaml
from src.logging import logger


# ---------------------------------------------------------------------------
# Per-format text extractors
# ---------------------------------------------------------------------------

def _extract_yaml(raw: bytes) -> str:
    """Load YAML bytes and return raw YAML string (for direct pass-through)."""
    text = raw.decode("utf-8", errors="replace")
    data = yaml.safe_load(text)
    if isinstance(data, dict):
        return yaml.dump(data, allow_unicode=True, sort_keys=False)
    return text


def _extract_json(raw: bytes) -> str:
    """Treat JSON as YAML (yaml.dump handles JSON natively)."""
    text = raw.decode("utf-8", errors="replace")
    data = yaml.safe_load(text)
    return yaml.dump(data, allow_unicode=True, sort_keys=False)


def _extract_text(raw: bytes) -> str:
    """Plain text / Markdown — return as-is."""
    return raw.decode("utf-8", errors="replace")


def _clean_extracted_text(text: str) -> str:
    """Normalize extractor output without changing resume content."""
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _looks_like_pdf_binary_decode(text: str) -> bool:
    """Detect PDF bytes decoded as text instead of real extracted content."""
    if not text:
        return True
    replacement_ratio = text.count("\ufffd") / max(len(text), 1)
    return len(text) > 100000 or replacement_ratio > 0.03 or text.lstrip().startswith("%PDF")


def _extract_pdf(raw: bytes) -> str:
    """Extract text from PDF using PyMuPDF first, then pdfminer."""
    errors: list[str] = []
    try:
        import fitz
        doc = fitz.open(stream=raw, filetype="pdf")
        pages = [page.get_text() or "" for page in doc]
        doc.close()
        text = _clean_extracted_text("\n".join(pages))
        if text and not _looks_like_pdf_binary_decode(text):
            logger.info("PDF text extracted: method=pymupdf chars={}", len(text))
            return text
        errors.append(f"pymupdf produced unusable text chars={len(text)}")
    except Exception as exc:
        errors.append(f"pymupdf failed: {exc!r}")

    try:
        from pdfminer.high_level import extract_text as pdfminer_extract_text
        text = _clean_extracted_text(pdfminer_extract_text(io.BytesIO(raw)) or "")
        if text and not _looks_like_pdf_binary_decode(text):
            logger.info("PDF text extracted: method=pdfminer chars={}", len(text))
            return text
        errors.append(f"pdfminer produced unusable text chars={len(text)}")
    except Exception as exc:
        errors.append(f"pdfminer failed: {exc!r}")

    # Last resort for malformed text-like PDFs. This should be rare; log loudly
    # because binary-looking output will hurt the LLM extraction step.
    text = raw.decode("utf-8", errors="replace")
    logger.warning(
        "PDF text extraction fell back to raw decode: chars={} errors={}",
        len(text),
        errors,
    )
    return text


def _extract_docx(raw: bytes) -> str:
    """Extract text from DOCX using python-docx."""
    from docx import Document
    doc = Document(io.BytesIO(raw))
    parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text.strip())
    return "\n".join(parts)


def _extract_html(raw: bytes) -> str:
    """Strip HTML tags, return plain text."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(raw.decode("utf-8", errors="replace"), "html.parser")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def _extract_latex(raw: bytes) -> str:
    """Strip LaTeX commands, keep readable text."""
    text = raw.decode("utf-8", errors="replace")
    # Extract body if present
    m = re.search(r"\\begin\{document\}(.*?)\\end\{document\}", text, re.DOTALL)
    if m:
        text = m.group(1)
    # Remove comments (lines starting with %)
    text = re.sub(r"(?m)^%.*$", "", text)
    # Remove common block commands and their content (like \begin{itemize}...\end{itemize})
    text = re.sub(
        r"\\begin\{(?:itemize|enumerate|description|equation|tabular|figure|table|center|flushleft|flushright|quote|verbatim)\*?\}.*?\\end\{(?:itemize|enumerate|description|equation|tabular|figure|table|center|flushleft|flushright|quote|verbatim)\*?\}",
        "",
        text,
        flags=re.DOTALL,
    )
    # Remove formatting commands that wrap content (keep the inner text)
    # First: extract the argument from commands like \textbf{Hello}
    text = re.sub(r"\\[a-zA-Z]+\*?\{([^{}]*)\}", r"\1", text)
    # Then: remove any remaining commands (no arguments left)
    text = re.sub(r"\\[a-zA-Z]+\*?", "", text)
    text = re.sub(r"\\[a-zA-Z]", "", text)
    # Remove remaining braces and special chars
    text = re.sub(r"[\{\}\^_~$&%#]", "", text)
    text = re.sub(r"\\\\", "\n", text)  # \\ -> newline
    text = re.sub(r"~", " ", text)     # ~ -> space
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


_EXTRACTORS = {
    ".yaml":     _extract_yaml,
    ".yml":      _extract_yaml,
    ".json":     _extract_json,
    ".txt":      _extract_text,
    ".md":       _extract_text,
    ".markdown": _extract_text,
    ".pdf":      _extract_pdf,
    ".docx":     _extract_docx,
    ".html":     _extract_html,
    ".htm":      _extract_html,
    ".tex":      _extract_latex,
    ".latex":    _extract_latex,
}


def extract_text(filename: str, raw: bytes) -> str:
    """Extract plain text from a document given its filename and bytes."""
    _, ext = os.path.splitext(filename.lower())
    extractor = _EXTRACTORS.get(ext, _extract_text)
    return extractor(raw)


# ---------------------------------------------------------------------------
# Empty / skeleton resume template
# ---------------------------------------------------------------------------

def _empty_resume() -> dict:
    """Return an empty resume skeleton."""
    return {
        "personal_information": {
            "name": "", "surname": "", "date_of_birth": "",
            "country": "", "zip_code": "", "city": "", "address": "",
            "phone_prefix": "+1", "phone": "", "email": "",
            "github": "", "linkedin": "",
        },
        "education_details": [],
        "experience_details": [],
        "projects": [],
        "achievements": [],
        "certifications": [],
        "languages": [],
        "interests": [],
    }


# ---------------------------------------------------------------------------
# LLM-based structured extraction
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE_ZH = """你是一个专业的简历解析助手。请从以下简历文本中提取信息，并严格按照以下 YAML 格式返回（不要添加任何说明文字，直接输出 YAML）：

```yaml
personal_information:
  name: "名字"
  surname: "姓氏"
  date_of_birth: "DD/MM/YYYY 或空字符串"
  country: "国家"
  zip_code: "邮编"
  city: "城市"
  address: "详细地址"
  phone_prefix: "+区号"
  phone: "电话号码"
  email: "邮箱"
  github: "GitHub URL 或空字符串"
  linkedin: "LinkedIn URL 或空字符串"
education_details:
  - education_level: "学历，如 Bachelor's Degree"
    institution: "学校名称"
    field_of_study: "专业"
    final_evaluation_grade: "GPA 或空字符串"
    year_of_completion: "毕业年份"
    start_date: "入学年份 或空字符串"
    additional_info: {}
experience_details:
  - position: "职位名称"
    company: "公司名称"
    employment_period: "YYYY-MM - YYYY-MM 或空字符串"
    location: "城市，国家"
    industry: "行业"
    key_responsibilities:
      - responsibility: "职责描述"
    skills_acquired:
      - "技能名称"
projects:
  - name: "项目名称"
    description: "项目描述"
    link: "URL 或空字符串"
achievements:
  - name: "成就名称"
    description: "描述"
certifications:
  - name: "证书名称"
    description: "描述"
languages:
  - language: "语言"
    proficiency: "Native / Fluent / Intermediate / Beginner"
interests:
  - "兴趣爱好"
```

注意：
1. 只输出 YAML，不要添加 markdown 代码块标记
2. 所有字段都尽量填满，空字段用空字符串 "" 表示
3. 不要遗漏任何信息，即使文本中未明确说明也不要臆造
4. 列表项目（experience、education 等）至少保留一个条目占位

以下是简历文本：
---
$resume_text
---
"""


_PROMPT_TEMPLATE_EN = """You are a professional resume parsing assistant. Extract information from the resume text below and return it strictly in the following YAML format (output YAML only, no explanatory text):

```yaml
personal_information:
  name: "First name"
  surname: "Last name"
  date_of_birth: "DD/MM/YYYY or empty string"
  country: "Country"
  zip_code: "Postal code"
  city: "City"
  address: "Full address"
  phone_prefix: "+Country code"
  phone: "Phone number"
  email: "Email"
  github: "GitHub URL or empty string"
  linkedin: "LinkedIn URL or empty string"
education_details:
  - education_level: "Degree, e.g. Bachelor's Degree"
    institution: "University name"
    field_of_study: "Major"
    final_evaluation_grade: "GPA or empty string"
    year_of_completion: "Graduation year"
    start_date: "Start year or empty string"
    additional_info: {}
experience_details:
  - position: "Job title"
    company: "Company name"
    employment_period: "YYYY-MM - YYYY-MM or empty string"
    location: "City, Country"
    industry: "Industry"
    key_responsibilities:
      - responsibility: "Responsibility description"
    skills_acquired:
      - "Skill name"
projects:
  - name: "Project name"
    description: "Project description"
    link: "URL or empty string"
achievements:
  - name: "Achievement name"
    description: "Description"
certifications:
  - name: "Certification name"
    description: "Description"
languages:
  - language: "Language"
    proficiency: "Native / Fluent / Intermediate / Beginner"
interests:
  - "Interest"
```

Notes:
1. Output YAML only, no markdown code fences
2. Fill all fields; use empty string "" for missing fields
3. Do not omit any information found in the text
4. Keep at least one entry placeholder for list fields

Resume text:
---
$resume_text
---
"""


def _call_llm(prompt: str, api_key: str, model_type: str = "anthropic",
              base_url: str = "https://api.minimaxi.com/anthropic", model_name: str = "") -> str:
    """Call the LLM with a prompt and return the text response.

    Uses the underlying LLM client directly (not LoggerChatModel.__call__,
    which expects to be part of a LangChain chain). Returns the raw AIMessage.
    """
    from src.libs.resume_and_cover_builder.llm.llm_generate_resume import (
        _create_chat_model,
    )
    import config as cfg

    try:
        normalized_model_type, normalized_base_url, normalized_protocol = _normalize_llm_settings(
            model_type=model_type,
            base_url=base_url,
        )

        # This extractor uses langchain-openai==0.1.x via ChatOpenAI, which
        # does not natively support the Responses API. For structured resume
        # extraction, chat completions are sufficient, so we downgrade the
        # protocol here for compatibility.
        if normalized_protocol == "openai_response":
            normalized_protocol = "openai_chat"

        logger.info(
            "Document parse LLM config: model_type={} protocol={} base_url={} prompt_chars={}",
            normalized_model_type,
            normalized_protocol,
            normalized_base_url,
            len(prompt),
        )

        cfg.LLM_MODEL_TYPE = normalized_model_type
        cfg.LLM_API_URL = normalized_base_url
        if model_name:
            cfg.LLM_MODEL = model_name
            cfg.ANTHROPIC_MODEL = model_name
            cfg.OPENAI_MODEL = model_name
        cfg.LLM_PROTOCOL = normalized_protocol
        if normalized_protocol == "anthropic":
            cfg.ANTHROPIC_BASE_URL = normalized_base_url
            cfg.ANTHROPIC_AUTH_TOKEN = api_key

        client = _create_chat_model(api_key)

        # Call the underlying chat model directly with a HumanMessage.
        # This avoids both LangChain's template .format() parser (which
        # chokes on curly braces in the resume text) AND the dict-format
        # issue with LoggerChatModel.__call__.
        from langchain_core.messages import HumanMessage
        result = client.invoke([HumanMessage(content=prompt)])

        # Extract content (handle both string and list-of-blocks)
        if hasattr(result, "content"):
            content = result.content
        else:
            content = result

        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            content = "".join(parts)

        content = (str(content) if content else "").strip()
        logger.info(
            "Document parse LLM raw output: chars={} preview={}",
            len(content),
            content[:400].replace("\n", "\\n"),
        )
        return content
    except Exception as e:
        raise RuntimeError(f"LLM extraction failed: {e}") from e


def _strip_path(base_url: str, protocol: str = "openai_chat") -> str:
    if not base_url:
        return base_url
    try:
        parsed = urlparse(base_url)
        path = (parsed.path or "").rstrip("/")

        if protocol == "anthropic":
            if path.endswith("/v1/messages"):
                path = path[: -len("/v1/messages")]
            elif path.endswith("/messages"):
                path = path[: -len("/messages")]
        else:
            for suffix in ("/chat/completions", "/completions", "/responses"):
                if path.endswith(suffix):
                    path = path[: -len(suffix)]
                    break

        return urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")).rstrip("/")
    except Exception:
        return base_url.rstrip("/")


def _normalize_llm_settings(model_type: str, base_url: str) -> tuple[str, str, str]:
    raw_model = (model_type or "").strip().lower()
    raw_url = (base_url or "").strip()
    protocol = "anthropic"
    normalized_model_type = "anthropic"

    if raw_model in {"openai", "openai_chat", "deepseek", "moonshot", "qwen", "doubao", "yi", "zhipu", "ollama", "minimax-chat"}:
        protocol = "openai_chat"
        normalized_model_type = "openai"
    elif raw_model in {"openai_response", "openai-resp", "minimax-resp"}:
        protocol = "openai_response"
        normalized_model_type = "openai"
    elif raw_model in {"anthropic", "claude", "minimax-anth"}:
        protocol = "anthropic"
        normalized_model_type = "anthropic"
    elif "minimaxi.com/anthropic" in raw_url:
        protocol = "anthropic"
        normalized_model_type = "anthropic"
    elif "openai.com" in raw_url or "minimaxi.com/v1" in raw_url:
        protocol = "openai_chat"
        normalized_model_type = "openai"

    normalized_base_url = _strip_path(raw_url, protocol=protocol) if raw_url else ""

    if "minimaxi.com" in normalized_base_url and protocol in {"openai_chat", "openai_response"}:
        if "/anthropic" in normalized_base_url:
            normalized_base_url = "https://api.minimaxi.com/v1"
        elif normalized_base_url == "https://api.minimaxi.com":
            normalized_base_url = "https://api.minimaxi.com/v1"

    if not normalized_base_url:
        normalized_base_url = (
            "https://api.minimaxi.com/anthropic"
            if protocol == "anthropic"
            else "https://api.minimaxi.com/v1"
        )

    return normalized_model_type, normalized_base_url, protocol


def _extract_yaml_candidate(raw_output: str) -> str:
    """Extract the most likely YAML payload from an LLM response."""
    text = raw_output.strip()
    if not text:
        return ""

    fenced = re.search(r"```(?:yaml|yml)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).strip()

    text = re.sub(r"^```yaml\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # If the model adds prose before YAML, start at the first known top-level key.
    marker_positions = [
        pos for pos in (
            text.find("personal_information:"),
            text.find("education_details:"),
            text.find("experience_details:"),
            text.find("projects:"),
        )
        if pos >= 0
    ]
    if marker_positions:
        text = text[min(marker_positions):].strip()

    return text


def _parse_llm_yaml_output(raw_output: str, diagnostics: dict[str, Any] | None = None) -> dict:
    """Parse the LLM's YAML output into a Python dict.

    The LLM sometimes wraps output in ```yaml ... ``` fences or
    has leading/trailing text. Strip those before parsing.
    """
    text = _extract_yaml_candidate(raw_output)
    if diagnostics is not None:
        diagnostics["llm_yaml_candidate_chars"] = len(text)
    logger.info(
        "Document parse YAML candidate: chars={} preview={}",
        len(text),
        text[:600].replace("\n", "\\n"),
    )

    if not text:
        if diagnostics is not None:
            diagnostics["llm_yaml_parse_success"] = False
            diagnostics["llm_yaml_error"] = "empty_yaml_candidate"
        logger.warning("Document parse YAML candidate is empty")
        return _empty_resume()

    try:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            if diagnostics is not None:
                diagnostics["llm_yaml_parse_success"] = False
                diagnostics["llm_yaml_error"] = f"non_dict_yaml:{type(data).__name__}"
            logger.warning(
                "Document parse YAML returned non-dict: type={} preview={}",
                type(data).__name__,
                repr(data)[:300],
            )
            return _empty_resume()
        if diagnostics is not None:
            diagnostics["llm_yaml_parse_success"] = True
            diagnostics["llm_yaml_error"] = ""
        logger.info(
            "Document parse YAML parsed: keys={} personal_fields={} education_count={} experience_count={} project_count={}",
            list(data.keys())[:12],
            _count_nonempty_personal_fields(data),
            len(data.get("education_details") or []),
            len(data.get("experience_details") or []),
            len(data.get("projects") or []),
        )
        return data
    except yaml.YAMLError as e:
        # Try to recover: find the first { and last } to extract YAML object
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = yaml.safe_load(text[start:end + 1])
                if isinstance(data, dict) and (
                    _has_meaningful_value(data)
                    or any(key in data for key in ("personal_information", "education_details", "experience_details", "projects"))
                ):
                    if diagnostics is not None:
                        diagnostics["llm_yaml_parse_success"] = True
                        diagnostics["llm_yaml_error"] = ""
                    logger.info(
                        "Document parse YAML recovered from brace block: keys={}",
                        list(data.keys())[:12],
                    )
                    return data
                logger.warning(
                    "Document parse brace recovery returned unusable value: type={} preview={}",
                    type(data).__name__,
                    repr(data)[:300],
                )
            except Exception as recovery_exc:
                logger.warning("Document parse brace recovery failed: {}", recovery_exc)
        if diagnostics is not None:
            diagnostics["llm_yaml_parse_success"] = False
            diagnostics["llm_yaml_error"] = str(e)
        logger.warning(
            "Document parse YAML failed: error={} candidate_preview={}",
            e,
            text[:600].replace("\n", "\\n"),
        )
        return _empty_resume()


def _has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_meaningful_value(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_meaningful_value(item) for item in value)
    return True


def _is_effectively_empty(data: dict[str, Any]) -> bool:
    return not _has_meaningful_value(data)


def _looks_like_chinese_text(text: str) -> bool:
    if not text:
        return False
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    return len(chinese_chars) >= 30


def _count_nonempty_personal_fields(data: dict[str, Any]) -> int:
    personal = data.get("personal_information") or {}
    return sum(1 for value in personal.values() if isinstance(value, str) and value.strip())


def _should_fallback_to_heuristic(data: dict[str, Any], plain_text: str) -> tuple[bool, str]:
    if _is_effectively_empty(data):
        return True, "llm_output_effectively_empty"

    personal = data.get("personal_information") or {}
    has_email_in_text = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", plain_text))
    has_phone_in_text = bool(re.search(r"\b1\d{10}\b", plain_text))
    has_email_in_output = bool(str(personal.get("email") or "").strip())
    has_phone_in_output = bool(str(personal.get("phone") or "").strip())

    if has_email_in_text and not has_email_in_output and has_phone_in_text and not has_phone_in_output:
        return True, "llm_missed_basic_contact_fields"

    if len(plain_text) >= 1200:
        section_counts = (
            len(data.get("education_details") or []),
            len(data.get("experience_details") or []),
            len(data.get("projects") or []),
        )
        if sum(section_counts) == 0 and _count_nonempty_personal_fields(data) <= 1:
            return True, "llm_output_sparse_for_long_resume"

    return False, ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_document(
    filename: str,
    raw: bytes,
    *,
    api_key: str = "",
    model_type: str = "anthropic",
    model_name: str = "",
    base_url: str = "https://api.minimaxi.com/anthropic",
    target_lang: str = "en",
    diagnostics: dict[str, Any] | None = None,
) -> dict:
    """Parse a resume document and return a dict matching plain_text_resume.yaml.

    Strategy:
        YAML / JSON  →  yaml.safe_load  (zero cost, exact)
        All other    →  extract text → LLM structured extraction
        No API key   →  lightweight heuristic fallback
    """
    _, ext = os.path.splitext(filename.lower())
    if diagnostics is not None:
        diagnostics.update({
            "llm_attempted": False,
            "llm_call_success": False,
            "llm_yaml_parse_success": False,
            "used_fallback": False,
            "fallback_reason": "",
            "extracted_text_chars": 0,
            "llm_raw_chars": 0,
            "llm_yaml_candidate_chars": 0,
            "llm_yaml_error": "",
        })

    # Tier 1: direct structured parse for YAML / JSON
    if ext in (".yaml", ".yml", ".json"):
        try:
            text = raw.decode("utf-8", errors="replace")
            data = yaml.safe_load(text)
            if isinstance(data, dict):
                return data
        except Exception:
            pass  # Fall through to LLM

    # Tier 2: extract plain text
    plain_text = extract_text(filename, raw)
    if diagnostics is not None:
        diagnostics["extracted_text_chars"] = len(plain_text)

    if not plain_text.strip():
        if diagnostics is not None:
            diagnostics["used_fallback"] = True
            diagnostics["fallback_reason"] = "empty_extracted_text"
        return _empty_resume()

    # No API key → heuristic fallback
    if not api_key:
        if diagnostics is not None:
            diagnostics["used_fallback"] = True
            diagnostics["fallback_reason"] = "missing_api_key"
        return _heuristic_fallback_v2(plain_text)

    # Tier 3: LLM structured extraction
    # Use string.Template instead of .format() so that curly braces in
    # the resume text are treated as literal characters, not placeholders.
    from string import Template
    prompt_lang = "zh" if (target_lang == "zh" or _looks_like_chinese_text(plain_text)) else "en"
    logger.info(
        "Document parse prompt selection: target_lang={} prompt_lang={} text_chars={} chinese_like={}",
        target_lang,
        prompt_lang,
        len(plain_text),
        _looks_like_chinese_text(plain_text),
    )
    prompt_template_str = _PROMPT_TEMPLATE_ZH if prompt_lang == "zh" else _PROMPT_TEMPLATE_EN
    prompt_template = Template(prompt_template_str)
    prompt = prompt_template.substitute(resume_text=plain_text[:12000])

    if diagnostics is not None:
        diagnostics["llm_attempted"] = True
    raw_output = _call_llm(
        prompt,
        api_key=api_key,
        model_type=model_type,
        model_name=model_name,
        base_url=base_url,
    )
    if diagnostics is not None:
        diagnostics["llm_call_success"] = True
        diagnostics["llm_raw_chars"] = len(raw_output)
    parsed = _parse_llm_yaml_output(raw_output, diagnostics=diagnostics)
    should_fallback, fallback_reason = _should_fallback_to_heuristic(parsed, plain_text)
    if should_fallback:
        if diagnostics is not None:
            diagnostics["used_fallback"] = True
            diagnostics["fallback_reason"] = fallback_reason
        logger.warning(
            "Document parse fallback triggered: reason={} personal_fields={} education_count={} experience_count={} project_count={}",
            fallback_reason,
            _count_nonempty_personal_fields(parsed),
            len(parsed.get("education_details") or []),
            len(parsed.get("experience_details") or []),
            len(parsed.get("projects") or []),
        )
        return _heuristic_fallback_v2(plain_text)
    return parsed


# ---------------------------------------------------------------------------
# Fallback: lightweight heuristic (used when no API key is available)
# ---------------------------------------------------------------------------

def _heuristic_fallback(text: str) -> dict:
    """Best-effort extraction when LLM is unavailable.

    Conservative — only extracts fields it is confident about (email, phone,
    URLs, name). Everything else gets a skeleton that the user fills in.
    """
    personal: dict[str, Any] = {}
    lines = text.splitlines()

    for line in lines[:50]:
        s = line.strip()
        if not s:
            continue
        # Email
        if m := re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", s):
            personal.setdefault("email", m.group(0))
        # Phone
        if "phone" not in personal and (m := re.search(r"[\+]?[\d\s\-().]{7,}", s)):
            phone_raw = re.sub(r"\s+", "", m.group(0))
            if len(phone_raw) >= 7:
                personal["phone"] = phone_raw
                personal["phone_prefix"] = "+1"
        # GitHub
        if m := re.search(r"https?://github\.com/[^\s]+", s, re.IGNORECASE):
            personal.setdefault("github", m.group(0))
        # LinkedIn
        if m := re.search(r"https?://linkedin\.com/in/[^\s]+", s, re.IGNORECASE):
            personal.setdefault("linkedin", m.group(0))

    # Name — first short line without special chars or digits
    name_parts = []
    for line in lines[:10]:
        s = line.strip()
        if 2 <= len(s) <= 60 and re.match(r"^[\w\u4e00-\u9fff\s.-]+$", s):
            if "@" not in s and not re.search(r"\d{4}", s) and s not in name_parts:
                name_parts = s.split(maxsplit=1)
                break

    personal.setdefault("name", name_parts[0] if name_parts else "")
    if len(name_parts) > 1:
        personal.setdefault("surname", name_parts[1])

    for field in ["date_of_birth", "country", "zip_code", "city", "address"]:
        personal.setdefault(field, "")

    result = _empty_resume()
    result["personal_information"] = personal
    return result


def _heuristic_fallback_v2(text: str) -> dict:
    """Richer fallback for resume-like plain text extracted from PDFs."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    personal: dict[str, Any] = {}
    result = _empty_resume()

    for idx, line in enumerate(lines[:120]):
        if "@" in line:
            email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", line)
            phone_match = re.search(r"\b1\d{10}\b", line)
            if email_match:
                personal["email"] = email_match.group(0)
            if phone_match:
                personal["phone"] = phone_match.group(0)
                personal["phone_prefix"] = "+86"
            if idx > 0:
                prev = lines[idx - 1]
                if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", prev):
                    personal["name"] = prev[0]
                    personal["surname"] = prev[1:] if len(prev) > 1 else ""
            break

    for line in lines[:120]:
        if m := re.search(r"https?://github\.com/[^\s]+", line, re.IGNORECASE):
            personal.setdefault("github", m.group(0))
        if m := re.search(r"https?://linkedin\.com/in/[^\s]+", line, re.IGNORECASE):
            personal.setdefault("linkedin", m.group(0))

    if "name" not in personal:
        for line in lines[:20]:
            if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", line):
                personal["name"] = line[0]
                personal["surname"] = line[1:] if len(line) > 1 else ""
                break

    for field, default in [
        ("date_of_birth", ""),
        ("country", "China"),
        ("zip_code", ""),
        ("city", ""),
        ("address", ""),
        ("phone_prefix", "+86" if personal.get("phone") else ""),
    ]:
        personal.setdefault(field, default)

    result["personal_information"] = personal

    date_line_pattern = re.compile(r"(\d{4})年(\d{2})月\s*-\s*(\d{4})年(\d{2})月")
    degree_keywords = ("本科", "硕士", "博士", "专科")

    edu_seen: set[str] = set()
    for i in range(1, len(lines) - 2):
        date_match = date_line_pattern.search(lines[i])
        if not date_match or not any(keyword in lines[i + 1] for keyword in degree_keywords):
            continue
        institution = lines[i - 1]
        if institution in {"211", "双一流"} and i >= 2:
            institution = lines[i - 2]
        if not institution or institution in edu_seen:
            continue
        degree_line = lines[i + 1]
        degree = next((keyword for keyword in degree_keywords if keyword in degree_line), "")
        major = degree_line.split(degree)[0].strip() if degree else degree_line
        start_year, _, end_year, _ = date_match.groups()
        result["education_details"].append({
            "education_level": degree,
            "institution": institution,
            "field_of_study": major,
            "final_evaluation_grade": "",
            "year_of_completion": end_year,
            "start_date": start_year,
            "additional_info": {},
        })
        edu_seen.add(institution)

    exp_seen: set[tuple[str, str, str]] = set()
    for i in range(0, len(lines) - 4):
        date_match = date_line_pattern.search(lines[i + 1])
        if not date_match:
            continue
        company = lines[i]
        position_line = lines[i + 2]
        if any(keyword in position_line for keyword in degree_keywords):
            continue
        key = (company, position_line, lines[i + 1])
        if key in exp_seen:
            continue
        location = lines[i + 3] if len(lines[i + 3]) <= 20 else ""
        responsibilities = []
        for j in range(i + 4, min(i + 8, len(lines))):
            candidate = lines[j]
            if date_line_pattern.search(candidate):
                break
            if len(candidate) >= 12:
                responsibilities.append({"responsibility": candidate})
        if not responsibilities:
            continue
        start_year, start_month, end_year, end_month = date_match.groups()
        result["experience_details"].append({
            "position": position_line,
            "company": company,
            "employment_period": f"{start_year}-{start_month} - {end_year}-{end_month}",
            "location": location,
            "industry": "",
            "key_responsibilities": responsibilities[:3],
            "skills_acquired": [],
        })
        exp_seen.add(key)

    project_seen: set[str] = set()
    for i in range(0, len(lines) - 2):
        date_match = date_line_pattern.search(lines[i + 1])
        if not date_match:
            continue
        title = lines[i]
        if len(title) > 40 or title in project_seen:
            continue
        desc_lines = []
        for j in range(i + 2, min(i + 6, len(lines))):
            candidate = lines[j]
            if date_line_pattern.search(candidate):
                break
            if len(candidate) >= 10:
                desc_lines.append(candidate)
        if desc_lines and any(token in "".join(desc_lines) for token in ("项目", "平台", "系统", "相机", "算法", "识别", "开发", "设计")):
            result["projects"].append({
                "name": title,
                "description": " ".join(desc_lines[:3]),
                "link": "",
            })
            project_seen.add(title)

    for line in lines:
        if line.startswith("荣誉/奖项：") or line.startswith("荣誉/奖项:"):
            award_part = re.split(r"荣誉/奖项[:：]", line, maxsplit=1)[-1]
            for item in [x.strip() for x in re.split(r"[、，]", award_part) if x.strip()]:
                result["achievements"].append({"name": item, "description": item})
        elif line.startswith("证书/执照：") or line.startswith("证书/执照:"):
            cert_part = re.split(r"证书/执照[:：]", line, maxsplit=1)[-1].strip()
            if cert_part:
                result["certifications"].append({"name": cert_part, "description": cert_part})
        elif line.startswith("语言：") or line.startswith("语言:"):
            lang_part = re.split(r"语言[:：]", line, maxsplit=1)[-1].strip()
            if lang_part:
                result["languages"].append({"language": lang_part, "proficiency": "Intermediate"})
        elif line.startswith("兴趣爱好：") or line.startswith("兴趣爱好:"):
            interest_part = re.split(r"兴趣爱好[:：]", line, maxsplit=1)[-1]
            result["interests"] = [item.strip() for item in re.split(r"[，,、]", interest_part) if item.strip()]
        elif line.startswith("技能：") or line.startswith("技能:"):
            skill_part = re.split(r"技能[:：]", line, maxsplit=1)[-1]
            skill_items = [item.strip(" ，,。") for item in re.split(r"[，,]", skill_part) if item.strip()]
            if result["experience_details"]:
                existing = result["experience_details"][0]["skills_acquired"]
                for skill in skill_items[:10]:
                    if skill not in existing:
                        existing.append(skill)
            elif skill_items:
                result["experience_details"].append({
                    "position": "",
                    "company": "",
                    "employment_period": "",
                    "location": "",
                    "industry": "",
                    "key_responsibilities": [],
                    "skills_acquired": skill_items[:10],
                })

    return result
