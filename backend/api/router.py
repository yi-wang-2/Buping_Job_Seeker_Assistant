"""API router aggregation."""

from fastapi import APIRouter

from backend.api.endpoints import ai_metrics, ai_skills, resume, interview, settings, history, job_tracker, memory

api_router = APIRouter(prefix="/api")

api_router.include_router(resume.router, prefix="/resume", tags=["resume"])
api_router.include_router(interview.router, prefix="/interview", tags=["interview"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(history.router, prefix="/history", tags=["history"])
api_router.include_router(job_tracker.router, prefix="/job-tracker", tags=["job-tracker"])
api_router.include_router(memory.router, prefix="/memory", tags=["memory"])
api_router.include_router(ai_metrics.router, prefix="/ai-metrics", tags=["ai-metrics"])
api_router.include_router(ai_skills.router, prefix="/ai", tags=["ai-skills"])
