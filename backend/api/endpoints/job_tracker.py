"""Job Tracker API endpoints — persist application records to the project folder."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parents[3] / "data_folder" / "job_tracker"
DATA_FILE = DATA_DIR / "records.json"


# ---- Pydantic models ----

class JobEntry(BaseModel):
    id: int
    company: str
    role: str
    base: str
    remark: str
    link: str
    status: str
    icon: str
    notes: str


class JobTrackerData(BaseModel):
    records: list[JobEntry]


# ---- Helpers ----

def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_records() -> list[dict]:
    _ensure_dir()
    if not DATA_FILE.exists():
        return []
    try:
        raw = DATA_FILE.read_text("utf-8")
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "records" in data:
            return data["records"]
        return []
    except (json.JSONDecodeError, OSError):
        return []


def _save_records(records: list[dict]) -> None:
    _ensure_dir()
    DATA_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
