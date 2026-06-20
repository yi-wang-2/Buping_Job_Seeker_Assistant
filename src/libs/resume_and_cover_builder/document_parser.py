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
from typing import Any

import yaml


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


def _extract_pdf(raw: bytes) -> str:
    """Extract text from PDF using PyMuPDF (fitz)."""
    try:
        import fitz
        doc = fitz.open(stream=raw, filetype="pdf")
        pages = [page.get_text() or "" for page in doc]
        doc.close()
        return "\n".join(pages)
    except Exception:
        # Fallback: try to decode as plain text (for broken/scanned PDFs)
        return raw.decode("utf-8", errors="replace")


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
              base_url: str = "https://api.minimaxi.com/anthropic") -> str:
    """Call the LLM with a prompt and return the text response.

    Uses the underlying LLM client directly (not LoggerChatModel.__call__,
    which expects to be part of a LangChain chain). Returns the raw AIMessage.
    """
    from src.libs.resume_and_cover_builder.llm.llm_generate_resume import (
        _create_chat_model,
    )

    try:
        client = _create_chat_model(api_key)

        # Override base_url if provided
        if base_url:
            try:
                import config as cfg
                if model_type == "anthropic":
                    cfg.ANTHROPIC_BASE_URL = base_url
                else:
                    cfg.LLM_API_URL = base_url
            except Exception:
                pass

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

        return (str(content) if content else "").strip()
    except Exception as e:
        raise RuntimeError(f"LLM extraction failed: {e}") from e


def _parse_llm_yaml_output(raw_output: str) -> dict:
    """Parse the LLM's YAML output into a Python dict.

    The LLM sometimes wraps output in ```yaml ... ``` fences or
    has leading/trailing text. Strip those before parsing.
    """
    text = raw_output.strip()
    text = re.sub(r"^```yaml\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    if not text:
        return _empty_resume()

    try:
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else _empty_resume()
    except yaml.YAMLError as e:
        # Try to recover: find the first { and last } to extract YAML object
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = yaml.safe_load(text[start:end + 1])
                return data if isinstance(data, dict) else _empty_resume()
            except Exception:
                pass
        raise ValueError(f"Invalid YAML from LLM: {e}") from e


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_document(
    filename: str,
    raw: bytes,
    *,
    api_key: str = "",
    model_type: str = "anthropic",
    base_url: str = "https://api.minimaxi.com/anthropic",
    target_lang: str = "en",
) -> dict:
    """Parse a resume document and return a dict matching plain_text_resume.yaml.

    Strategy:
        YAML / JSON  →  yaml.safe_load  (zero cost, exact)
        All other    →  extract text → LLM structured extraction
        No API key   →  lightweight heuristic fallback
    """
    _, ext = os.path.splitext(filename.lower())

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

    if not plain_text.strip():
        return _empty_resume()

    # No API key → heuristic fallback
    if not api_key:
        return _heuristic_fallback(plain_text)

    # Tier 3: LLM structured extraction
    # Use string.Template instead of .format() so that curly braces in
    # the resume text are treated as literal characters, not placeholders.
    from string import Template
    prompt_template_str = _PROMPT_TEMPLATE_ZH if target_lang == "zh" else _PROMPT_TEMPLATE_EN
    prompt_template = Template(prompt_template_str)
    prompt = prompt_template.substitute(resume_text=plain_text[:12000])

    raw_output = _call_llm(
        prompt,
        api_key=api_key,
        model_type=model_type,
        base_url=base_url,
    )
    return _parse_llm_yaml_output(raw_output)


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
