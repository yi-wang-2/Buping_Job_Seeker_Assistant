"""FastAPI application entrypoint for Buping (不平)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.router import api_router

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan."""
    # Ensure output directories exist
    (ROOT / "data_folder" / "output").mkdir(parents=True, exist_ok=True)
    (ROOT / "data_folder" / "output" / "interview_prep").mkdir(parents=True, exist_ok=True)
    (ROOT / "data_folder" / "output" / "mock_interview").mkdir(parents=True, exist_ok=True)
    (ROOT / "data_folder" / "job_tracker").mkdir(parents=True, exist_ok=True)
    (ROOT / "data_folder" / "job_tracker" / "icon").mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="不平 (Buping)",
        version="0.2.0",
        description="AI-powered career assistant for resume generation, interview prep and mock interviews.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router)

    # Serve job tracker icons from the project data folder
    JOB_TRACKER_ICON = ROOT / "data_folder" / "job_tracker" / "icon"
    app.mount("/api/job-tracker/icon", StaticFiles(directory=str(JOB_TRACKER_ICON)), name="job_tracker_icon")

    # Serve frontend static files in production
    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")

    return app


app = create_app()
