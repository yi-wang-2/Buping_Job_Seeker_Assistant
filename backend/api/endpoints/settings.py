"""Settings API endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services import config_service

router = APIRouter()


class SettingsResponse(BaseModel):
    llm_api_key: str = ""
    llm_model_type: str = "anthropic"
    llm_base_url: str = "https://api.minimaxi.com/anthropic"
    resume_language: str = "zh"
    system_language: str = "zh"


class SaveSettingsRequest(BaseModel):
    llm_api_key: str = ""
    llm_model_type: str = "anthropic"
    llm_base_url: str = ""
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
        resume_language=secrets.get("resume_language", "zh"),
        system_language=secrets.get("system_language", "zh"),
    )


@router.put("")
def save_settings(req: SaveSettingsRequest) -> dict:
    """Save settings."""
    config_service.save_secrets({
        "llm_api_key": req.llm_api_key,
        "llm_model_type": req.llm_model_type,
        "llm_base_url": req.llm_base_url,
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
