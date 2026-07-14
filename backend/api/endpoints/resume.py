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
    model_type: str = ""
    model_name: str = ""
    base_url: str = ""
    llm_protocol: str = ""  # "anthropic" | "openai_chat" | "openai_response" — empty = auto
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


# ---------------------------------------------------------------------------
# AI 智能改写助手
# ---------------------------------------------------------------------------

# Four rewrite modes matching the design in docs/ROADMAP.md §1
VALID_REWRITE_MODES = {
    "more_quantified",  # 📏 更量化 (数字 + 数据)
    "more_professional",  # 🎯 更专业 (行业术语)
    "more_concise",  # ✨ 更简洁 (去除冗余)
    "fix_grammar",  # 🔧 修正语法
}


class RewriteRequest(BaseModel):
    text: str  # Selected text from the editor
    mode: str = "more_quantified"  # One of VALID_REWRITE_MODES
    context: str = ""  # Optional surrounding context (helps LLM understand)
    target_language: str = "zh"  # Output language: "zh" | "en"
    api_key: str = ""
    model_type: str = ""
    model_name: str = ""
    base_url: str = ""
    llm_protocol: str = ""


class RewriteResponse(BaseModel):
    status: str
    original: str
    rewritten: str
    mode: str
    message: str = ""


@router.get("/rewrite/modes")
def get_rewrite_modes() -> dict:
    """Return the available rewrite modes (for UI population)."""
    return {
        "modes": [
            {
                "id": "more_quantified",
                "icon": "📏",
                "label_zh": "更量化",
                "label_en": "More Quantified",
                "desc_zh": "增加数字、百分比、具体数据支撑",
                "desc_en": "Add numbers, percentages, concrete data",
            },
            {
                "id": "more_professional",
                "icon": "🎯",
                "label_zh": "更专业",
                "label_en": "More Professional",
                "desc_zh": "使用行业术语和专业表达",
                "desc_en": "Use industry jargon and professional phrasing",
            },
            {
                "id": "more_concise",
                "icon": "✨",
                "label_zh": "更简洁",
                "label_en": "More Concise",
                "desc_zh": "去除冗余，表达更紧凑",
                "desc_en": "Remove redundancy, tighter wording",
            },
            {
                "id": "fix_grammar",
                "icon": "🔧",
                "label_zh": "修正语法",
                "label_en": "Fix Grammar",
                "desc_zh": "修正拼写、语法、标点错误",
                "desc_en": "Correct spelling, grammar, punctuation",
            },
        ]
    }


@router.post("/rewrite", response_model=RewriteResponse)
async def rewrite_text(req: RewriteRequest) -> RewriteResponse:
    """AI 智能改写助手 — rewrite a selected text snippet.

    Used by the WYSIWYG editor's "AI Rewrite" feature. Calls the LLM
    with a mode-specific system prompt and returns the rewritten text.

    API credentials are resolved with the same 3-level fallback as
    generate_resume(): explicit param → secrets.yaml → config.py.
    """
    if req.mode not in VALID_REWRITE_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{req.mode}'. Must be one of: {sorted(VALID_REWRITE_MODES)}",
        )
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Text to rewrite cannot be empty")

    try:
        rewritten = await asyncio.to_thread(
            resume_service.rewrite_text,
            text=req.text,
            mode=req.mode,
            context=req.context,
            target_language=req.target_language,
            api_key=req.api_key,
            model_type=req.model_type,
            model_name=req.model_name,
            base_url=req.base_url,
            llm_protocol=req.llm_protocol,
        )
        return RewriteResponse(
            status="success",
            original=req.text,
            rewritten=rewritten,
            mode=req.mode,
            message="改写成功",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rewrite failed: {e}")


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
            model_name=req.model_name,
            base_url=req.base_url,
            llm_protocol=req.llm_protocol or None,
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


# ---------------------------------------------------------------------------
# Save edited HTML (from WYSIWYG editor) → PDF + HTML pair
# ---------------------------------------------------------------------------

class SaveEditedRequest(BaseModel):
    html: str  # Full HTML document from the iframe
    filename_base: str = "resume_edited"


class SaveEditedResponse(BaseModel):
    status: str
    pdf_filename: str
    html_filename: str
    pdf_size: int
    message: str = ""


@router.post("/save-edited", response_model=SaveEditedResponse)
async def save_edited(req: SaveEditedRequest) -> SaveEditedResponse:
    """Convert edited HTML directly to PDF and save to output folder.

    Used by the WYSIWYG editor's Save button: the user edits the rendered
    resume in the iframe and clicks Save. We render that HTML to PDF
    (no LLM call) and persist both PDF + HTML so the new version
    appears in the history list.

    The filename pair (pdf + html) shares the same timestamp so they
    can be paired together when previewing later.
    """
    if not req.html or not req.html.strip():
        raise HTTPException(status_code=400, detail="HTML content cannot be empty")
    try:
        result = await asyncio.to_thread(
            resume_service.convert_html_to_pdf,
            html_content=req.html,
            filename_base=req.filename_base or "resume_edited",
        )
        return SaveEditedResponse(
            status="success",
            pdf_filename=result["pdf_filename"],
            html_filename=result["html_filename"],
            pdf_size=result["pdf_size"],
            message="编辑版已保存到历史记录",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save failed: {e}")
