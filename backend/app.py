"""FastAPI application entrypoint for Buping (不平)."""

from __future__ import annotations

import logging
import asyncio
import contextlib
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
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
RADAR_SYNC_HOUR = 6


def followup_schedule_hours(interval_hours: int, anchor_hour: int = 4) -> tuple[int, ...]:
    if interval_hours not in {4, 6, 8, 12, 24}:
        interval_hours = 8
    return tuple(sorted({(anchor_hour + offset) % 24 for offset in range(0, 24, interval_hours)}))


def latest_scheduled_time(now: datetime, hours: tuple[int, ...]) -> datetime:
    candidates = [now.replace(hour=hour, minute=0, second=0, microsecond=0) for hour in hours]
    due = [candidate for candidate in candidates if candidate <= now]
    return max(due) if due else (candidates[-1] - timedelta(days=1))


def next_scheduled_time(now: datetime, hours: tuple[int, ...]) -> datetime:
    candidates = [now.replace(hour=hour, minute=0, second=0, microsecond=0) for hour in hours]
    future = [candidate for candidate in candidates if candidate > now]
    return min(future) if future else (candidates[0] + timedelta(days=1))


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
    radar_sync_task = None
    radar_match_task = None
    followup_check_task = None
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
        radar_auto_enabled = os.getenv("BUPING_JOB_RADAR_AUTO_SYNC", "1").lower() not in {"0", "false", "no"}
        radar_match_enabled = os.getenv("BUPING_JOB_RADAR_AUTO_MATCH", "1").lower() not in {"0", "false", "no"}
        radar_match_interval = max(300, int(os.getenv("BUPING_JOB_RADAR_MATCH_INTERVAL_SECONDS", "1800")))
        radar_match_batch = max(1, min(5, int(os.getenv("BUPING_JOB_RADAR_MATCH_BATCH", "1"))))
        followup_auto_enabled = os.getenv("BUPING_JOB_FOLLOWUP_AUTO_CHECK", "1").lower() not in {"0", "false", "no"}
        if radar_auto_enabled or radar_match_enabled or followup_auto_enabled:
            from backend.api.endpoints import job_tracker
            from backend.services import job_radar_service

            async def radar_sync_loop() -> None:
                attempted_date = None
                while True:
                    now = datetime.now().astimezone()
                    today_run = now.replace(hour=RADAR_SYNC_HOUR, minute=0, second=0, microsecond=0)
                    last_sync = job_radar_service.get_stats().get("last_sync")
                    last_sync_date = None
                    if last_sync and last_sync.get("created_at"):
                        with contextlib.suppress(ValueError):
                            last_sync_date = datetime.fromisoformat(last_sync["created_at"]).astimezone().date()
                    catch_up = now >= today_run and attempted_date != now.date() and last_sync_date != now.date()
                    next_run = now + timedelta(seconds=5) if catch_up else today_run
                    if not catch_up and next_run <= now:
                        next_run += timedelta(days=1)
                    await asyncio.sleep((next_run - now).total_seconds())
                    settings = job_radar_service.get_radar_settings()
                    attempted_date = datetime.now().astimezone().date()
                    if radar_auto_enabled and settings["auto_sync"]:
                        try:
                            await asyncio.to_thread(job_radar_service.sync_tencent_sheet, settings["source_url"])
                            logger.info("Job Radar automatic sync completed")
                        except Exception:
                            logger.exception("Job Radar automatic sync failed")
            async def followup_check_loop() -> None:
                attempted_slot: datetime | None = None
                while True:
                    now = datetime.now().astimezone()
                    schedule = job_tracker.get_followup_schedule()
                    hours = followup_schedule_hours(schedule["interval_hours"], schedule["anchor_hour"])
                    due_slot = latest_scheduled_time(now, hours)
                    if attempted_slot != due_slot:
                        await asyncio.sleep(5)
                    else:
                        next_slot = next_scheduled_time(now, hours)
                        # Re-read user settings promptly instead of sleeping through a changed interval.
                        await asyncio.sleep(min((next_slot - now).total_seconds(), 60))
                    # Recompute after wake/sleep so multiple missed slots collapse to the latest one.
                    now = datetime.now().astimezone()
                    schedule = job_tracker.get_followup_schedule()
                    hours = followup_schedule_hours(schedule["interval_hours"], schedule["anchor_hour"])
                    due_slot = latest_scheduled_time(now, hours)
                    if attempted_slot == due_slot:
                        continue
                    attempted_slot = due_slot
                    try:
                        result = await asyncio.to_thread(job_tracker.run_followup_all)
                        await asyncio.to_thread(job_tracker.record_followup_run, due_slot, result)
                        logger.info(
                            "Job follow-up scheduled check completed for %s: %s records",
                            due_slot.strftime("%Y-%m-%d %H:%M"), result.get("checked", 0),
                        )
                    except Exception as exc:
                        await asyncio.to_thread(job_tracker.record_followup_run, due_slot, None, str(exc))
                        logger.exception("Job follow-up automatic check failed")

            async def radar_match_loop() -> None:
                # Let API startup settle before launching the first browser crawl.
                await asyncio.sleep(15)
                while True:
                    try:
                        result = await asyncio.to_thread(
                            job_radar_service.auto_fill_linked_jobs,
                            radar_match_batch,
                        )
                        if result["processed"]:
                            logger.info(
                                "Job Radar automatic matching processed %s companies: %s",
                                result["processed"], result["results"],
                            )
                    except Exception:
                        logger.exception("Job Radar automatic matching failed")
                    await asyncio.sleep(radar_match_interval)

            if radar_auto_enabled:
                radar_sync_task = asyncio.create_task(radar_sync_loop())
            if radar_match_enabled:
                radar_match_task = asyncio.create_task(radar_match_loop())
            if followup_auto_enabled:
                followup_check_task = asyncio.create_task(followup_check_loop())
    try:
        yield
    finally:
        if cleanup_task:
            cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cleanup_task
        if radar_sync_task:
            radar_sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await radar_sync_task
        if radar_match_task:
            radar_match_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await radar_match_task
        if followup_check_task:
            followup_check_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await followup_check_task


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
