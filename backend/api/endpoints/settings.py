"""Settings API endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.services import config_service
from src.libs.resume_and_cover_builder.document_parser import parse_document

router = APIRouter()


class SettingsResponse(BaseModel):
    llm_api_key: str = ""
    llm_model_type: str = "anthropic"
    llm_base_url: str = "https://api.minimaxi.com/anthropic"
    llm_protocol: str = "anthropic"  # "anthropic" | "openai_chat" | "openai_response"
    resume_language: str = "zh"
    system_language: str = "zh"


class SaveSettingsRequest(BaseModel):
    llm_api_key: str = ""
    llm_model_type: str = "anthropic"
    llm_base_url: str = ""
    llm_protocol: str = "anthropic"
    resume_language: str = "zh"
    system_language: str = "zh"


@router.get("", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    """Get current settings."""
    secrets = config_service.load_secrets()
    return SettingsResponse(
        llm_api_key=secrets.get("llm_api_key", ""),
        llm_model_type=secrets.get("llm_model_type", "anthropic"),
        llm_base_url=secrets.get("llm_base_url", "https://api.minimaxi.com/anthropic"),
        llm_protocol=secrets.get("llm_protocol", "anthropic"),
        resume_language=secrets.get("resume_language", "zh"),
        system_language=secrets.get("system_language", "zh"),
    )


@router.put("")
def save_settings(req: SaveSettingsRequest) -> dict:
    """Save settings."""
    # Validate protocol value
    valid_protocols = {"anthropic", "openai_chat", "openai_response"}
    protocol = req.llm_protocol if req.llm_protocol in valid_protocols else "anthropic"

    config_service.save_secrets({
        "llm_api_key": req.llm_api_key,
        "llm_model_type": req.llm_model_type,
        "llm_base_url": req.llm_base_url,
        "llm_protocol": protocol,
        "resume_language": req.resume_language,
        "system_language": req.system_language,
    })
    return {"status": "success", "message": "配置已保存！"}


class ResumeContentRequest(BaseModel):
    content: str
    language: str = "zh"


@router.get("/resume-content")
def get_resume_content(language: str = "zh") -> dict:
    """Get resume YAML content."""
    content = config_service.load_resume_content(language)
    return {"content": content, "language": language}


@router.put("/resume-content")
def save_resume_content(req: ResumeContentRequest) -> dict:
    """Save resume YAML content."""
    config_service.save_resume_content(req.content, req.language)
    return {"status": "success", "message": "简历内容已保存！"}


SUPPORTED_EXTENSIONS = {
    ".yaml", ".yml", ".json", ".txt", ".md",
    ".pdf", ".docx", ".html", ".htm", ".tex",
}


@router.post("/upload-resume")
async def upload_resume(
    file: UploadFile = File(...),
    target_lang: str = "en",
    api_key: str = "",
    model_type: str = "anthropic",
    base_url: str = "https://api.minimaxi.com/anthropic",
) -> dict:
    """Upload a resume document and extract structured YAML data.

    Supports: YAML, JSON, Markdown, plain text, PDF, DOCX, HTML, LaTeX.
    Returns extracted data as a YAML string for user review before saving.

    Strategy:
        - YAML / JSON  →  yaml.safe_load  (zero LLM cost, exact)
        - Other formats →  extract text → LLM structured extraction
        - Without API key → heuristic fallback (email/phone/URLs only)
    """
    import os

    filename = Path(file.filename or "resume").resolve()
    _, ext = os.path.splitext(filename.name.lower())

    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{ext}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        )

    # Enforce a sane size limit (5 MB)
    MAX_SIZE = 5 * 1024 * 1024
    content = b""
    while chunk := await file.read(65536):
        content += chunk
        if len(content) > MAX_SIZE:
            raise HTTPException(
                status_code=413,
                detail="File too large. Maximum size is 5 MB.",
            )

    # 3-level API key fallback (same as resume_service)
    if not api_key:
        try:
            secrets = config_service.load_secrets()
            api_key = secrets.get("llm_api_key", "")
            if not model_type or model_type == "anthropic":
                model_type = secrets.get("llm_model_type", model_type)
            if base_url == "https://api.minimaxi.com/anthropic":
                base_url = secrets.get("llm_base_url", base_url)
        except Exception:
            pass
    if not api_key:
        try:
            import config as cfg
            api_key = cfg.ANTHROPIC_AUTH_TOKEN or cfg.LLM_API_KEY or ""
        except Exception:
            pass

    # Set base_url in config for LLM to pick up
    if base_url:
        try:
            import config as cfg
            cfg.ANTHROPIC_BASE_URL = base_url
            cfg.LLM_API_URL = base_url
        except Exception:
            pass

    try:
        data = parse_document(
            filename.name,
            content,
            api_key=api_key,
            model_type=model_type,
            base_url=base_url,
            target_lang=target_lang,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse document: {e}")

    # Dump to YAML string for display in the editor
    import yaml

    yaml_str = yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)

    return {
        "status": "success",
        "filename": filename.name,
        "ext": ext,
        "yaml_content": yaml_str,
        "message": "文档解析成功，请在下方编辑器中检查并修改内容，然后保存。",
    }
