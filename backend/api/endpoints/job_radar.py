"""Job radar endpoints for local imports and recommendations."""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from backend.api.endpoints import job_tracker
from backend.services import job_radar_service


router = APIRouter()
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class SyncUrlRequest(BaseModel):
    source_url: str = Field(min_length=10, max_length=1000)


class JobActionRequest(BaseModel):
    action: str
    enabled: bool = True


class JobPreferencesRequest(BaseModel):
    target_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    acceptable_locations: list[str] = Field(default_factory=list)
    excluded_locations: list[str] = Field(default_factory=list)
    recruitment_types: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    company_types: list[str] = Field(default_factory=list)
    preferred_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    company_blacklist: list[str] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)


class TrackJobRequest(BaseModel):
    company: str = Field(default="", max_length=200)
    role: str = Field(default="", max_length=200)
    base: str = Field(default="", max_length=300)
    recruitment_type: str = Field(default="", max_length=200)
    link: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=10000)


@router.post("/sync-url")
async def sync_url(req: SyncUrlRequest) -> dict:
    try:
        return await asyncio.to_thread(job_radar_service.sync_job_source, req.source_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"岗位源读取失败：{exc}") from exc


@router.post("/import")
async def import_jobs(
    file: UploadFile = File(...),
    source_url: str = Form(default=""),
    source_name: str = Form(default="腾讯文档岗位表"),
) -> dict:
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件不能超过 20 MB")
    try:
        return job_radar_service.import_file(file.filename or "jobs.xlsx", raw, source_url, source_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/recommendations")
def recommendations(
    limit: int = Query(default=100, ge=1, le=500),
    min_score: float = Query(default=0, ge=0, le=100),
    query: str = Query(default="", max_length=100),
    company_type: str = Query(default="", max_length=50),
    match_level: str = Query(default="", max_length=20),
    recruitment_type: str = Query(default="", max_length=20),
    favorite_only: bool = Query(default=False),
    scene: str = Query(default="general", pattern="^(general|state_owned|civil_service)$"),
) -> dict:
    return job_radar_service.list_recommendations(
        limit=limit, min_score=min_score, query=query, company_type=company_type,
        match_level=match_level, recruitment_type=recruitment_type, favorite_only=favorite_only, scene=scene,
    )


@router.get("/daily")
def daily_recommendations(
    scene: str = Query(default="general", pattern="^(general|state_owned|civil_service)$"),
) -> dict:
    return job_radar_service.daily_recommendations(limit=3, scene=scene)


@router.post("/{job_id}/linked-recommendations")
async def linked_recommendations(job_id: str) -> dict:
    try:
        return await asyncio.to_thread(job_radar_service.recommend_linked_jobs, job_id, 3)
    except (ValueError, LookupError) as exc:
        status = 404 if isinstance(exc, LookupError) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"岗位详情读取失败：{exc}") from exc


@router.get("/{job_id}/linked-jobs")
def cached_linked_jobs(job_id: str, limit: int = Query(default=500, ge=1, le=1000)) -> dict:
    try:
        return job_radar_service.list_linked_jobs(job_id, limit=limit)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/stats")
def stats() -> dict:
    return job_radar_service.get_stats()


@router.get("/preferences")
def get_preferences() -> dict:
    return job_radar_service.get_user_preferences()


@router.put("/preferences")
def save_preferences(req: JobPreferencesRequest) -> dict:
    return {"status": "ok", "preferences": job_radar_service.save_user_preferences(req.model_dump())}


@router.put("/{job_id}/action")
def update_job_action(job_id: str, req: JobActionRequest) -> dict:
    try:
        return {"status": "ok", **job_radar_service.set_job_action(job_id, req.action, req.enabled)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{job_id}/track")
def track_job(job_id: str, req: TrackJobRequest | None = None) -> dict:
    job = job_radar_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")
    records = job_tracker._load_records()
    confirmed = req.model_dump() if req else {}
    link = confirmed.get("link") or job.get("link", "")
    duplicate = next((item for item in records if item.get("link") and item.get("link") == link), None)
    if duplicate:
        if req:
            duplicate.update({
                "company": confirmed.get("company") or duplicate.get("company", ""),
                "role": confirmed.get("role") or duplicate.get("role", ""),
                "base": confirmed.get("base") or duplicate.get("base", ""),
                "remark": " / ".join(filter(None, [confirmed.get("recruitment_type"), "岗位雷达"])),
                "link": link,
                "notes": confirmed.get("notes") or duplicate.get("notes", ""),
            })
            job_tracker._save_records(records)
        job_radar_service.set_job_action(job_id, "applied", True)
        return {"status": "updated" if req else "exists", "record": duplicate}
    next_id = max((int(item.get("id", 0)) for item in records), default=0) + 1
    record = {
        "id": next_id,
        "company": confirmed.get("company") or job.get("company", ""),
        "role": confirmed.get("role") or job.get("role", "") or "招聘岗位",
        "base": confirmed.get("base") or job.get("location", ""),
        "remark": " / ".join(filter(None, [confirmed.get("recruitment_type") or job.get("recruitment_type", ""), "岗位雷达"])),
        "applied_at": datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M"),
        "link": link,
        "status": "简历筛选",
        "icon": "",
        "notes": confirmed.get("notes") or "\n".join(filter(None, [job.get("industry", ""), job.get("description", ""), job.get("referral", "")])),
    }
    records.append(record)
    job_tracker._save_records(records)
    job_radar_service.set_job_action(job_id, "applied", True)
    return {"status": "added", "record": record}
