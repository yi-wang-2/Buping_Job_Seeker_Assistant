"""Resume generation API endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.services import resume_service

router = APIRouter()


class GenerateResumeRequest(BaseModel):
    api_key: str = ""
    model_type: str = "anthropic"
    base_url: str = "https://api.minimaxi.com/anthropic"
    style_name: str = ""
    job_description: Optional[str] = None
    resume_language: str = "zh"
    system_language: str = "zh"


class GenerateResumeResponse(BaseModel):
    path: str
    filename: str
    status: str


@router.get("/styles")
def get_styles() -> dict:
    """Get available resume styles."""
    return resume_service.get_available_styles()


@router.post("/generate", response_model=GenerateResumeResponse)
def generate_resume(req: GenerateResumeRequest) -> GenerateResumeResponse:
    """Generate a resume PDF."""
    try:
        result = resume_service.generate_resume(
            api_key=req.api_key,
            model_type=req.model_type,
            base_url=req.base_url,
            style_name=req.style_name,
            job_description=req.job_description,
            resume_language=req.resume_language,
            system_language=req.system_language,
        )
        return GenerateResumeResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{filename}")
def download_resume(filename: str) -> FileResponse:
    """Download a generated resume PDF."""
    from pathlib import Path

    file_path = Path("data_folder/output") / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=str(file_path), filename=filename, media_type="application/pdf")
