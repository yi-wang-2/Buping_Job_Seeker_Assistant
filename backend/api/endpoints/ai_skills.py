from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.ai_skill_service import (
    advise_career,
    analyze_job_description,
    list_archived_jobs,
    match_skills,
)

router = APIRouter()


class JDAnalyzeRequest(BaseModel):
    job_description: str = Field(min_length=1)
    api_key: str = ""
    provider: str = ""
    model: str = ""
    base_url: str = ""
    source_url: str = ""


class SkillMatchRequest(BaseModel):
    resume: str = Field(min_length=1)
    job_description: str = Field(min_length=1)
    api_key: str = ""
    provider: str = ""
    model: str = ""
    base_url: str = ""


class CareerAdviceRequest(BaseModel):
    resume: str = Field(min_length=1)
    preferences: str = ""
    goals: str = ""
    history: str = ""
    api_key: str = ""
    provider: str = ""
    model: str = ""
    base_url: str = ""


@router.post("/jd/analyze")
def analyze_jd(req: JDAnalyzeRequest) -> dict[str, Any]:
    try:
        return analyze_job_description(
            req.job_description,
            api_key=req.api_key,
            provider=req.provider,
            model=req.model,
            base_url=req.base_url,
            source_url=req.source_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"JD analysis failed: {exc}") from exc


@router.get("/jd/history")
def jd_history(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
    return {"items": list_archived_jobs(limit)}


@router.post("/skill-match")
def skill_match(req: SkillMatchRequest) -> dict[str, Any]:
    try:
        return match_skills(**req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Skill matching failed: {exc}") from exc


@router.post("/career-advice")
def career_advice(req: CareerAdviceRequest) -> dict[str, Any]:
    try:
        return advise_career(**req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Career advice failed: {exc}") from exc
