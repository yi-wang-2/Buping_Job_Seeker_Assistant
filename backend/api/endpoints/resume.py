"""Resume generation API endpoints."""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
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


class PreviewResumeRequest(BaseModel):
    style_name: str = ""
    resume_language: str = "zh"


class PreviewResumeResponse(BaseModel):
    html: str
    style: str
    language: str


@router.get("/styles")
def get_styles() -> dict:
    """Get available resume styles."""
    return resume_service.get_available_styles()


@router.post("/generate", response_model=GenerateResumeResponse)
async def generate_resume(req: GenerateResumeRequest) -> GenerateResumeResponse:
    """Generate a resume PDF.

    Async endpoint to avoid blocking the FastAPI event loop during
    long-running LLM and Chrome operations.
    """
    try:
        result = await asyncio.to_thread(
            resume_service.generate_resume,
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


@router.post("/preview", response_model=PreviewResumeResponse)
async def preview_resume(req: PreviewResumeRequest) -> PreviewResumeResponse:
    """Generate a lightweight HTML preview from the local YAML resume.

    This does NOT invoke the LLM — it renders the local YAML data
    against the chosen CSS template so the user can see how the
    resume will look in a particular style within seconds.
    """
    try:
        result = await asyncio.to_thread(
            resume_service.generate_preview_html,
            style_name=req.style_name,
            resume_language=req.resume_language,
        )
        return PreviewResumeResponse(**result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preview/render", response_class=HTMLResponse)
async def preview_render(style: str = "", language: str = "zh") -> HTMLResponse:
    """Stand-alone preview HTML page (useful for direct browser visits)."""
    try:
        result = await asyncio.to_thread(
            resume_service.generate_preview_html,
            style_name=style,
            resume_language=language,
        )
        return HTMLResponse(content=result["html"])
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
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


@router.get("/preview-saved/{html_filename}")
async def preview_saved_resume(html_filename: str) -> dict:
    """Read a previously-saved HTML file for preview in the UI.

    The HTML file is generated and saved alongside the PDF whenever a
    resume is produced, allowing later re-preview without re-running
    the LLM.
    """
    import base64
    from pathlib import Path

    # Sanitize to prevent path traversal
    safe_name = Path(html_filename).name
    file_path = Path("data_folder/output") / safe_name
    if not file_path.exists() or not file_path.suffix == ".html":
        raise HTTPException(status_code=404, detail=f"Saved HTML not found: {safe_name}")
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read HTML: {e}")
    return {"html": content, "filename": safe_name}
