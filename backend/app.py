"""FastAPI application entrypoint for Buping (不平)."""

from __future__ import annotations

import logging
import asyncio
import contextlib
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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
    public_demo = os.getenv("BUPING_PUBLIC_DEMO", "").lower() in {"1", "true", "yes"}
    cleanup_task = None
    if public_demo:
        # Public mode must not write prompts, resumes, provider replies, or browser payloads to logs.
        from loguru import logger as loguru_logger
        from backend.services.resume_service import cleanup_public_artifacts
        from selenium.webdriver.remote.remote_connection import LOGGER as selenium_remote_logger

        loguru_logger.remove()
        loguru_logger.add(sys.stderr, level="WARNING")
        for noisy_logger in ("selenium", "urllib3", "httpcore", "httpx"):
            logging.getLogger(noisy_logger).setLevel(logging.WARNING)
        selenium_remote_logger.handlers.clear()
        selenium_remote_logger.addHandler(logging.NullHandler())
        selenium_remote_logger.setLevel(logging.WARNING)

        async def cleanup_loop() -> None:
            while True:
                await asyncio.to_thread(cleanup_public_artifacts)
                await asyncio.sleep(600)

        cleanup_task = asyncio.create_task(cleanup_loop())
    else:
        from src.libs.ai_engine.memory import SQLiteMemoryRepository
        SQLiteMemoryRepository(ROOT / "data_folder" / "ai_memory.sqlite3")
    try:
        yield
    finally:
        if cleanup_task:
            cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cleanup_task


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
        @app.get("/{full_path:path}", include_in_schema=False)
        async def frontend(full_path: str) -> FileResponse:
            requested = (FRONTEND_DIST / full_path).resolve()
            if requested.is_relative_to(FRONTEND_DIST.resolve()) and requested.is_file():
                return FileResponse(requested)
            return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
