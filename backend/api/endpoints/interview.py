"""Interview preparation and mock interview API endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services import interview_service

router = APIRouter()


# ---- Interview Prep ----

class InterviewPrepRequest(BaseModel):
    api_key: str = ""
    model_type: str = "anthropic"
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
    model_type: str = "anthropic"
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
    status: str


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
