"""AI coding practice API."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services import ai_coding_service

router = APIRouter()


class StartRequest(BaseModel):
    task_id: str


class SubmitRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20000)
    approach: str = Field(default="", max_length=5000)
    test_strategy: str = Field(default="", max_length=5000)
    ai_reflection: str = Field(default="", max_length=5000)


@router.get("/tasks")
def tasks() -> dict:
    return {"items": ai_coding_service.list_tasks()}


@router.post("/sessions/start")
def start(req: StartRequest) -> dict:
    try:
        return ai_coding_service.start_session(req.task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/submit")
def submit(session_id: str, req: SubmitRequest) -> dict:
    try:
        return ai_coding_service.submit_session(session_id=session_id, **req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sessions")
def sessions() -> dict:
    return {"items": ai_coding_service.list_sessions()}
