"""Settings API endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.services import config_service
from backend.services import notification_service
from backend.services.resume_validation import validate_resume_data
from src.libs.resume_and_cover_builder.document_parser import parse_document
from src.logging import logger

router = APIRouter()


class SettingsResponse(BaseModel):
    llm_api_key: str = ""
    llm_model_type: str = "anthropic"
    llm_model: str = "MiniMax-M3"
    llm_base_url: str = "https://api.minimaxi.com/anthropic"
    llm_protocol: str = "anthropic"  # "anthropic" | "openai_chat" | "openai_response"
    resume_language: str = "zh"
    system_language: str = "zh"


class SaveSettingsRequest(BaseModel):
    llm_api_key: str = ""
    llm_model_type: str = "anthropic"
    llm_model: str = ""
    llm_base_url: str = ""
    llm_protocol: str = "anthropic"
    resume_language: str = "zh"
    system_language: str = "zh"


class DiscoverModelsRequest(BaseModel):
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_protocol: str = "openai_chat"


class TestLLMConnectionRequest(BaseModel):
    llm_api_key: str = ""
    llm_model_type: str = "anthropic"
    llm_model: str = ""
    llm_base_url: str = ""


class NotificationSettingsRequest(BaseModel):
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_to: str = ""
    smtp_security: str = "ssl"
    wechat_enabled: bool = False
    serverchan_sendkey: str = ""


@router.get("", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    """Get current settings."""
    secrets = config_service.load_secrets()
    model_type = secrets.get("llm_model_type", "anthropic")
    model_name = config_service.resolve_llm_model(
        model_type,
        saved_model=secrets.get("llm_model", ""),
        saved_provider=secrets.get("llm_model_provider", ""),
    )
    protocol = secrets.get("llm_protocol", "anthropic")
    return SettingsResponse(
        llm_api_key=secrets.get("llm_api_key", ""),
        llm_model_type=model_type,
        llm_model=model_name,
        llm_base_url=secrets.get("llm_base_url", "https://api.minimaxi.com/anthropic"),
        llm_protocol=protocol,
        resume_language=secrets.get("resume_language", "zh"),
        system_language=secrets.get("system_language", "zh"),
    )


@router.put("")
def save_settings(req: SaveSettingsRequest) -> dict:
    """Save settings."""
    # Validate protocol value
    valid_protocols = {"anthropic", "openai_chat", "openai_response"}
    protocol = req.llm_protocol if req.llm_protocol in valid_protocols else "anthropic"

    model_name = config_service.resolve_llm_model(req.llm_model_type, req.llm_model)
    config_service.save_secrets({
        "llm_api_key": req.llm_api_key,
        "llm_model_type": req.llm_model_type,
        "llm_model": model_name,
        "llm_model_provider": req.llm_model_type,
        "llm_base_url": req.llm_base_url,
        "llm_protocol": protocol,
        "resume_language": req.resume_language,
        "system_language": req.system_language,
    })
    return {"status": "success", "message": "配置已保存！"}


@router.post("/models")
async def discover_models(req: DiscoverModelsRequest) -> dict:
    """Return models only when the provider exposes a compatible list endpoint."""
    models = await config_service.discover_llm_models(
        req.llm_api_key, req.llm_base_url, req.llm_protocol
    )
    return {"models": models}


@router.post("/llm/test")
def test_model_connection(req: TestLLMConnectionRequest) -> dict:
    """Test the exact unsaved LLM configuration entered by the user."""
    from backend.services.llm_connection_service import diagnose_llm_error, test_llm_connection

    try:
        return test_llm_connection(
            api_key=req.llm_api_key,
            provider=req.llm_model_type,
            model=req.llm_model,
            base_url=req.llm_base_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        code, message = diagnose_llm_error(exc)
        raise HTTPException(status_code=502, detail={"code": code, "message": message}) from exc


@router.get("/notifications")
def get_notification_settings() -> dict:
    return notification_service.get_settings()


@router.put("/notifications")
def save_notification_settings(req: NotificationSettingsRequest) -> dict:
    try:
        return {"status": "success", "settings": notification_service.save_settings(req.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/notifications/test")
def test_notifications() -> dict:
    result = notification_service.send_test_notification()
    if not result["results"]:
        raise HTTPException(status_code=400, detail="请先启用并保存至少一个通知渠道")
    return {"status": "success", **result}


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
    import yaml
    from src.libs.resume_and_cover_builder.document_parser import normalize_resume_data

    try:
        parsed = yaml.safe_load(req.content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid resume YAML: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="Resume YAML must be an object")

    normalized = normalize_resume_data(parsed)
    normalized_content = yaml.safe_dump(
        normalized,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    config_service.save_resume_content(normalized_content, req.language)
    validation = validate_resume_data(normalized)
    return {
        "status": "success",
        "message": "简历内容已保存！",
        "validation": validation,
        "content": normalized_content,
    }


SUPPORTED_EXTENSIONS = {
    ".yaml", ".yml", ".json", ".txt", ".md",
    ".pdf", ".docx", ".html", ".htm", ".tex",
}


@router.get("/resume-photo/status")
def get_resume_photo_status() -> dict:
    path = config_service.get_resume_photo_path()
    return {"uploaded": path is not None, "filename": path.name if path else ""}


@router.get("/resume-photo")
def get_resume_photo():
    path = config_service.get_resume_photo_path()
    if not path:
        raise HTTPException(status_code=404, detail="No resume photo uploaded")
    return FileResponse(path)


@router.post("/resume-photo")
async def upload_resume_photo(file: UploadFile = File(...)) -> dict:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in config_service.SUPPORTED_PHOTO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PNG, JPG and WebP photos are supported")
    content = await file.read(5 * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Photo file is empty")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Photo is too large. Maximum size is 5 MB")
    path = config_service.save_resume_photo(content, extension)
    return {"status": "success", "filename": path.name}


@router.delete("/resume-photo")
def delete_resume_photo() -> dict:
    deleted = config_service.delete_resume_photo()
    return {"status": "success", "deleted": deleted}


@router.post("/upload-resume")
async def upload_resume(
    file: UploadFile = File(...),
    target_lang: str = "en",
    api_key: str = "",
    model_type: str = "",
    model_name: str = "",
    base_url: str = "",
    llm_protocol: str = "",
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
            if not llm_protocol:
                llm_protocol = secrets.get("llm_protocol", "")
            if not model_name:
                model_name = secrets.get("llm_model", "")
            if not base_url:
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
            if llm_protocol:
                cfg.LLM_PROTOCOL = llm_protocol
            if model_name:
                cfg.LLM_MODEL = model_name
                cfg.ANTHROPIC_MODEL = model_name
                cfg.OPENAI_MODEL = model_name
        except Exception:
            pass

    try:
        logger.info(
            "Upload resume parse request: filename={} ext={} target_lang={} model_type={} llm_protocol={} base_url={}",
            filename.name,
            ext,
            target_lang,
            model_type,
            llm_protocol,
            base_url,
        )
        parse_diagnostics = {}
        data = parse_document(
            filename.name,
            content,
            api_key=api_key,
            model_type=model_type,
            model_name=model_name,
            base_url=base_url,
            target_lang=target_lang,
            diagnostics=parse_diagnostics,
        )
        logger.info(
            "Upload resume parse result: filename={} personal_fields={} education_count={} experience_count={} project_count={}",
            filename.name,
            sum(1 for v in (data.get("personal_information") or {}).values() if str(v).strip()),
            len(data.get("education_details") or []),
            len(data.get("experience_details") or []),
            len(data.get("projects") or []),
        )
        logger.info("Upload resume parse diagnostics: {}", parse_diagnostics)
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
        "parse_diagnostics": parse_diagnostics,
        "validation": validate_resume_data(data),
        "message": "文档解析成功，请在下方编辑器中检查并修改内容，然后保存。",
    }
