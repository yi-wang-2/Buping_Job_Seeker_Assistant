"""Job Tracker API endpoints — persist application records to the project folder."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.services import job_followup_service
from backend.services import notification_service

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parents[3] / "data_folder" / "job_tracker"
DATA_FILE = DATA_DIR / "records.json"
FOLLOWUP_SETTINGS_FILE = DATA_DIR / "followup_settings.json"
FOLLOWUP_RUNTIME_FILE = DATA_DIR / "followup_runtime.json"
ALLOWED_FOLLOWUP_INTERVALS = {4, 6, 8, 12, 24}
_STATUS_EVENT_SUBSCRIBERS: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[str]]] = set()
_STATUS_EVENT_LOCK = Lock()


# ---- Pydantic models ----

class StatusEvent(BaseModel):
    status: str
    raw_status: str = ""
    checked_at: str
    evidence_url: str = ""
    source: str = "website"


class JobEntry(BaseModel):
    id: int
    company: str
    role: str
    base: str
    remark: str
    applied_at: str = ""
    link: str
    status: str
    icon: str
    notes: str
    followup_enabled: bool = False
    followup_ai_enabled: bool = True
    followup_platform: str = ""
    followup_url: str = ""
    followup_state: str = "not_connected"
    last_checked_at: str = ""
    last_raw_status: str = ""
    last_check_message: str = ""
    last_parser: str = ""
    last_llm_confidence: float | None = None
    last_llm_tokens: int = 0
    last_llm_candidate_status: str = ""
    last_llm_candidate_evidence: str = ""
    last_llm_application_confidence: float | None = None
    last_llm_status_confidence: float | None = None
    last_llm_evidence_excerpt: str = ""
    last_application_statuses: list[dict] = Field(default_factory=list)
    last_notification: dict = Field(default_factory=dict)
    status_history: list[StatusEvent] = Field(default_factory=list)


class JobTrackerData(BaseModel):
    records: list[JobEntry]


class FollowupConnectionRequest(BaseModel):
    platform: str = ""
    portal_url: str


class FollowupCompleteRequest(BaseModel):
    platform: str


class FollowupScheduleRequest(BaseModel):
    interval_hours: int = 8


# ---- Helpers ----

def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _stop_rejected_followup(record: dict) -> bool:
    if "挂" in str(record.get("status") or "") and record.get("followup_enabled"):
        record["followup_enabled"] = False
        return True
    return False


def _load_records() -> list[dict]:
    _ensure_dir()
    if not DATA_FILE.exists():
        return []
    try:
        raw = DATA_FILE.read_text("utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return []
    records = data if isinstance(data, list) else data.get("records", []) if isinstance(data, dict) else []
    stopped = [_stop_rejected_followup(record) for record in records]
    if any(stopped):
        _save_records(records)
    return records


def _save_records(records: list[dict]) -> None:
    _ensure_dir()
    for record in records:
        _stop_rejected_followup(record)
    DATA_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_followup_schedule() -> dict:
    interval = 8
    if FOLLOWUP_SETTINGS_FILE.exists():
        try:
            interval = int(json.loads(FOLLOWUP_SETTINGS_FILE.read_text("utf-8")).get("interval_hours", 8))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            interval = 8
    if interval not in ALLOWED_FOLLOWUP_INTERVALS:
        interval = 8
    return {
        "interval_hours": interval,
        "anchor_hour": 4,
        "auto_enabled": os.getenv("BUPING_JOB_FOLLOWUP_AUTO_CHECK", "1").lower() not in {"0", "false", "no"},
        **get_followup_runtime(),
    }


def get_followup_runtime() -> dict:
    default = {
        "last_run_at": "",
        "last_scheduled_for": "",
        "last_run_status": "never",
        "last_checked": 0,
        "last_error": "",
    }
    if not FOLLOWUP_RUNTIME_FILE.exists():
        return default
    try:
        data = json.loads(FOLLOWUP_RUNTIME_FILE.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return {key: data.get(key, value) for key, value in default.items()}


def record_followup_run(due_slot: datetime, result: dict | None = None, error: str = "") -> dict:
    """Persist scheduler health so the UI can prove automatic checks are running."""
    _ensure_dir()
    runtime = {
        "last_run_at": datetime.now().astimezone().isoformat(),
        "last_scheduled_for": due_slot.isoformat(),
        "last_run_status": "error" if error else "success",
        "last_checked": int((result or {}).get("checked", 0)),
        "last_error": error,
    }
    FOLLOWUP_RUNTIME_FILE.write_text(
        json.dumps(runtime, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return runtime


def save_followup_schedule(interval_hours: int) -> dict:
    if interval_hours not in ALLOWED_FOLLOWUP_INTERVALS:
        raise ValueError("检查间隔仅支持 4、6、8、12 或 24 小时")
    _ensure_dir()
    FOLLOWUP_SETTINGS_FILE.write_text(
        json.dumps({"interval_hours": interval_hours}, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return get_followup_schedule()


def _apply_followup_result(record: dict, result: dict, *, notify: bool = False) -> bool:
    old_status = str(record.get("status") or "")
    record["last_checked_at"] = result.get("checked_at", "")
    record["followup_state"] = result.get("connection_state", record.get("followup_state", ""))
    record["last_raw_status"] = result.get("raw_status", "")
    record["last_check_message"] = result.get("message", "")
    record["last_parser"] = result.get("parser", "")
    record["last_llm_confidence"] = result.get("llm_confidence")
    record["last_llm_tokens"] = int((result.get("llm_usage") or {}).get("total_tokens", 0))
    record["last_llm_candidate_status"] = result.get("llm_candidate_status", "")
    record["last_llm_candidate_evidence"] = result.get("llm_candidate_evidence", "")
    record["last_llm_application_confidence"] = result.get("llm_application_confidence")
    record["last_llm_status_confidence"] = result.get("llm_status_confidence")
    record["last_llm_evidence_excerpt"] = result.get("llm_evidence_excerpt", "")
    record["last_application_statuses"] = result.get("application_statuses", [])
    new_status = result.get("status")
    status_changed = bool(new_status and new_status != old_status)
    if status_changed:
        record["status"] = new_status
        history = record.setdefault("status_history", [])
        history.append({
            "status": new_status,
            "raw_status": result.get("raw_status", ""),
            "checked_at": result.get("checked_at", ""),
            "evidence_url": result.get("evidence_url", ""),
            "source": "website",
        })
    _stop_rejected_followup(record)
    notification = None
    company = str(record.get("company") or "未知企业")
    role = str(record.get("role") or "未知岗位")
    if notify and status_changed:
        notification = _safe_notify(
            f"求职状态更新：{company}",
            f"企业：{company}\n岗位：{role}\n原状态：{old_status or '未记录'}\n新状态：{new_status}\n网站原文：{result.get('raw_status') or '无'}\n检查时间：{result.get('checked_at') or '未知'}",
            event_key=f"status:{record.get('id')}:{old_status}:{new_status}",
        )
    elif notify and result.get("result") in {"login_required", "verification_required"}:
        reason = "登录已失效" if result.get("result") == "login_required" else "网站要求人机验证"
        notification = _safe_notify(
            f"求职跟进需要处理：{company}",
            f"企业：{company}\n岗位：{role}\n问题：{reason}\n请打开不平，在求职记录中重新登录或完成验证。",
            event_key=f"auth:{record.get('id')}:{result.get('result')}",
            dedup_seconds=max(3600, get_followup_schedule()["interval_hours"] * 3600 - 300),
        )
    if notification:
        record["last_notification"] = notification
    return status_changed


def _enqueue_status_event(queue: asyncio.Queue[str], payload: str) -> None:
    if queue.full():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    queue.put_nowait(payload)


def _publish_status_changes(records: list[dict]) -> None:
    if not records:
        return
    payload = json.dumps({"records": records}, ensure_ascii=False)
    with _STATUS_EVENT_LOCK:
        subscribers = list(_STATUS_EVENT_SUBSCRIBERS)
    stale: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[str]]] = []
    for loop, queue in subscribers:
        try:
            loop.call_soon_threadsafe(_enqueue_status_event, queue, payload)
        except RuntimeError:
            stale.append((loop, queue))
    if stale:
        with _STATUS_EVENT_LOCK:
            for subscriber in stale:
                _STATUS_EVENT_SUBSCRIBERS.discard(subscriber)


def _safe_notify(title: str, body: str, **kwargs: object) -> dict:
    try:
        return notification_service.send_notification(title, body, **kwargs)
    except Exception as exc:
        return {"sent": 0, "results": [{"channel": "system", "status": "error", "error": str(exc)}]}


def run_followup_all() -> dict:
    records = _load_records()
    results = []
    changed_records = []
    for record in records:
        if not record.get("followup_enabled"):
            continue
        try:
            result = job_followup_service.check_application(record)
        except Exception as exc:
            result = {"result": "error", "connection_state": "error", "message": str(exc), "checked_at": ""}
        if _apply_followup_result(record, result, notify=True):
            changed_records.append(record.copy())
        results.append({"id": record.get("id"), **result})
    if results:
        _save_records(records)
    _publish_status_changes(changed_records)
    return {"status": "ok", "checked": len(results), "results": results}


# ---- Endpoints ----

@router.get("")
def get_records() -> dict:
    """Load all job tracker records from disk."""
    records = _load_records()
    return {"records": records, "count": len(records)}


@router.put("")
def save_records(payload: JobTrackerData) -> dict:
    """Save all job tracker records to disk."""
    try:
        records = [r.model_dump() for r in payload.records]
        _save_records(records)
        return {"status": "ok", "saved": len(records), "path": str(DATA_FILE)}
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to write records: {e}")


@router.get("/path")
def get_data_path() -> dict:
    """Return the on-disk path of the records file."""
    return {"path": str(DATA_FILE), "dir": str(DATA_DIR)}


@router.post("/followup/connect")
def connect_followup(req: FollowupConnectionRequest) -> dict:
    try:
        return job_followup_service.open_login_browser(req.platform, req.portal_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/followup/complete")
def complete_followup(req: FollowupCompleteRequest) -> dict:
    return job_followup_service.complete_login(req.platform)


@router.post("/followup/check-all")
def check_all_followups() -> dict:
    return run_followup_all()


@router.get("/followup/events")
async def followup_status_events() -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=10)
        subscriber = (loop, queue)
        with _STATUS_EVENT_LOCK:
            _STATUS_EVENT_SUBSCRIBERS.add(subscriber)
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"event: status-changed\ndata: {payload}\n\n"
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            with _STATUS_EVENT_LOCK:
                _STATUS_EVENT_SUBSCRIBERS.discard(subscriber)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/followup/schedule")
def get_followup_schedule_endpoint() -> dict:
    return get_followup_schedule()


@router.put("/followup/schedule")
def save_followup_schedule_endpoint(req: FollowupScheduleRequest) -> dict:
    try:
        return {"status": "success", **save_followup_schedule(req.interval_hours)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{entry_id}/followup/check")
def check_followup(entry_id: int) -> dict:
    records = _load_records()
    record = next((item for item in records if int(item.get("id", -1)) == entry_id), None)
    if not record:
        raise HTTPException(status_code=404, detail="求职记录不存在")
    try:
        result = job_followup_service.check_application(record, headless=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    status_changed = _apply_followup_result(record, result, notify=True)
    _save_records(records)
    if status_changed:
        _publish_status_changes([record.copy()])
    return {"status": "ok", "record": record, **result}


@router.get("/stats")
def get_stats() -> dict:
    """Return computed summary statistics over the records."""
    records = _load_records()

    total = len(records)
    interviewing = sum(
        1 for r in records
        if "面" in r.get("status", "") and "挂" not in r.get("status", "")
    )
    offers = sum(
        1 for r in records
        if r.get("status", "").lower() == "offer"
    )
    rejected = sum(
        1 for r in records
        if "挂" in r.get("status", "")
    )

    # Group by company prefix (first 2 chars)
    from collections import Counter
    company_counts = Counter()
    for r in records:
        name = r.get("company", "").strip()
        if name:
            company_counts[name] += 1

    return {
        "total": total,
        "interviewing": interviewing,
        "offers": offers,
        "rejected": rejected,
        "company_counts": dict(company_counts.most_common(20)),
    }
