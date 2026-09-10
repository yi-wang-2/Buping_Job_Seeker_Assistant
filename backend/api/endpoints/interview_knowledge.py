from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from backend.services.interview_knowledge_service import get_interview_knowledge_service
from src.libs.ai_engine.knowledge import KnowledgeQuery


router = APIRouter()


class SourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=300)
    source_type: Literal["git", "local_file", "markdown", "json", "pdf", "docx", "archive"]
    location: str = Field(min_length=1, max_length=1000)
    scope: Literal["public", "organization", "user", "session"] = "public"
    owner_id: str | None = Field(default=None, max_length=200)
    license: str | None = Field(default=None, max_length=200)
    domain_pack: str = Field(default="interview", max_length=200)


class SyncRequest(BaseModel):
    source: SourceRequest
    accept_warnings: bool = False


@router.get("/sources")
def list_sources(
    user_id: str = Query(default="local", max_length=200),
    session_id: str | None = Query(default=None, max_length=200),
) -> dict[str, Any]:
    return {"items": get_interview_knowledge_service().list_sources(user_id, session_id)}


@router.post("/preview")
def preview_source(request: SourceRequest) -> dict[str, Any]:
    try:
        return get_interview_knowledge_service().preview(request.model_dump())
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync")
def sync_source(request: SyncRequest) -> dict[str, Any]:
    try:
        return get_interview_knowledge_service().sync(
            request.source.model_dump(), accept_warnings=request.accept_warnings,
        )
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/search")
def search_knowledge(request: KnowledgeQuery) -> dict[str, Any]:
    return get_interview_knowledge_service().search(request.model_dump())


@router.post("/upload")
async def upload_knowledge(
    file: UploadFile = File(...), user_id: str = Form(default="local"),
    session_id: str | None = Form(default=None), domain_pack: str = Form(default="interview"),
) -> dict[str, Any]:
    try:
        return get_interview_knowledge_service().save_upload(
            filename=file.filename or "knowledge", content=await file.read(),
            user_id=user_id, session_id=session_id, domain_pack=domain_pack,
        )
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class SourceStatusRequest(BaseModel):
    enabled: bool
    user_id: str = Field(default="local", max_length=200)


@router.patch("/sources/{source_id}/status")
def set_source_status(source_id: str, request: SourceStatusRequest) -> dict[str, Any]:
    try:
        return get_interview_knowledge_service().set_enabled(
            source_id, request.enabled, user_id=request.user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/sources/{source_id}")
def delete_source(source_id: str, user_id: str = Query(default="local", max_length=200)) -> dict[str, bool]:
    try:
        deleted = get_interview_knowledge_service().delete_source(source_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="knowledge source not found")
    return {"deleted": True}
