"""Interview preparation and mock interview API endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from backend.services import interview_service

router = APIRouter()


# ---- Interview Prep ----

class InterviewPrepRequest(BaseModel):
    api_key: str = ""
    model_type: str = ""
    model_name: str = ""
    base_url: str = ""
    job_description: str = ""
    interview_type: str = "综合面试"
    question_count: int = 10
    resume_language: str = "zh"


class InterviewPrepResponse(BaseModel):
    report: str
    file_path: str
    status: str


@router.post("/prep", response_model=InterviewPrepResponse)
def generate_interview_prep(req: InterviewPrepRequest) -> InterviewPrepResponse:
    """Generate interview preparation report."""
    try:
        result = interview_service.generate_interview_prep(
            api_key=req.api_key,
            model_type=req.model_type,
            model_name=req.model_name,
            base_url=req.base_url,
            job_description=req.job_description,
            interview_type=req.interview_type,
            question_count=req.question_count,
            resume_language=req.resume_language,
        )
        return InterviewPrepResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- Mock Interview ----

class MockInterviewStartRequest(BaseModel):
    api_key: str = ""
    model_type: str = ""
    model_name: str = ""
    base_url: str = ""
    resume_text: str = ""
    job_description: str = ""
    company_name: str = ""
    company_industry: str = ""
    job_title: str = ""
    interview_type: str = "综合面试"
    interview_style: str = "专业型"


class MockInterviewStartResponse(BaseModel):
    history: list[dict]
    session_id: Optional[str] = None
    status: str


@router.post("/mock/start", response_model=MockInterviewStartResponse)
def start_mock_interview(req: MockInterviewStartRequest) -> MockInterviewStartResponse:
    """Start a mock interview session."""
    try:
        result = interview_service.start_mock_interview(
            api_key=req.api_key,
            model_type=req.model_type,
            model_name=req.model_name,
            base_url=req.base_url,
            resume_text=req.resume_text,
            job_description=req.job_description,
            company_name=req.company_name,
            company_industry=req.company_industry,
            job_title=req.job_title,
            interview_type=req.interview_type,
            interview_style=req.interview_style,
        )
        return MockInterviewStartResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class MockInterviewSubmitRequest(BaseModel):
    session_id: str
    user_message: str
    history: list[dict] = []
    context_window: int = 5


class MockInterviewSubmitResponse(BaseModel):
    history: list[dict]
    session_id: Optional[str] = None
    status: str


@router.post("/mock/submit", response_model=MockInterviewSubmitResponse)
def submit_mock_answer(req: MockInterviewSubmitRequest) -> MockInterviewSubmitResponse:
    """Submit an answer in a mock interview."""
    try:
        result = interview_service.submit_mock_answer(
            session_id=req.session_id,
            user_message=req.user_message,
            history=req.history,
            context_window=req.context_window,
        )
        return MockInterviewSubmitResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class MockInterviewEndRequest(BaseModel):
    session_id: str
    history: list[dict] = []


class MockInterviewEndResponse(BaseModel):
    evaluation: str
    file_path: str
    pdf_path: str = ""
    pdf_filename: str = ""
    status: str


class MockInterviewTTSRequest(BaseModel):
    text: str
    provider: str = "minimax"
    voice: str = ""
    rate: str = "+0%"


@router.get("/mock/tts/voices")
def get_mock_interview_tts_voices() -> dict:
    """List selectable voices that are available in the local runtime."""
    return interview_service.get_mock_interview_tts_voices()


@router.post("/mock/tts")
async def synthesize_mock_interview_tts(req: MockInterviewTTSRequest) -> Response:
    """Synthesize mock interviewer speech."""
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    try:
        audio, media_type = await interview_service.synthesize_mock_interview_speech(
            text=req.text,
            voice=req.voice,
            rate=req.rate,
            provider=req.provider,
        )
        return Response(
            content=audio,
            media_type=media_type,
            headers={"Cache-Control": "no-store"},
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mock/tts/stream")
async def stream_mock_interview_tts(req: MockInterviewTTSRequest) -> StreamingResponse:
    """Stream mock interviewer speech."""
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    try:
        if (req.provider or "minimax").lower() == "minimax":
            interview_service.validate_minimax_tts_config()
        return StreamingResponse(
            interview_service.stream_mock_interview_speech(
                text=req.text,
                voice=req.voice,
                rate=req.rate,
                provider=req.provider,
            ),
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mock/tts/diagnostics")
def get_mock_interview_tts_diagnostics() -> dict:
    """Return TTS runtime diagnostics."""
    return interview_service.get_tts_diagnostics()


@router.post("/mock/end", response_model=MockInterviewEndResponse)
def end_mock_interview(req: MockInterviewEndRequest) -> MockInterviewEndResponse:
    """End a mock interview and generate evaluation."""
    try:
        result = interview_service.end_mock_interview(
            session_id=req.session_id,
            history=req.history,
        )
        return MockInterviewEndResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mock/download/{filename}")
def download_mock_interview_pdf(filename: str) -> FileResponse:
    """Download a generated mock interview PDF report."""
    from pathlib import Path

    safe_name = Path(filename).name
    if not safe_name.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF reports can be downloaded")

    file_path = Path("data_folder/output/mock_interview") / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path=str(file_path), filename=safe_name, media_type="application/pdf")
