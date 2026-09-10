from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from src.libs.ai_engine.memory import MemoryItem, SQLiteMemoryRepository

router = APIRouter()


def repository() -> SQLiteMemoryRepository:
    return SQLiteMemoryRepository()


class MemoryWriteRequest(BaseModel):
    namespace: str = Field(min_length=1, max_length=80)
    key: str = Field(min_length=1, max_length=120)
    value: Any
    source: str = "user"
    confidence: float = Field(default=1.0, ge=0, le=1)
    importance: int = Field(default=50, ge=0, le=100)


class MemorySettingsRequest(BaseModel):
    memory_enabled: bool
    cache_enabled: bool


class MemoryReviewRequest(BaseModel):
    accepted: bool


def serialize(item: MemoryItem) -> dict[str, Any]:
    data = asdict(item)
    for field in ("created_at", "updated_at", "expires_at"):
        data[field] = data[field].isoformat() if data[field] else None
    return data


@router.get("")
def list_memory(namespace: str = "") -> dict[str, Any]:
    return {"items": [serialize(item) for item in repository().list_memories(namespace=namespace)]}


@router.post("")
def write_memory(req: MemoryWriteRequest) -> dict[str, Any]:
    item = repository().upsert_memory(MemoryItem(**req.model_dump()))
    return serialize(item)


@router.get("/candidates")
def list_memory_candidates() -> dict[str, Any]:
    items = repository().list_memory_candidates()
    for item in items:
        item.pop("value_json", None)
    return {"items": items}


@router.post("/candidates/{candidate_id}/review")
def review_memory_candidate(candidate_id: str, req: MemoryReviewRequest) -> dict[str, Any]:
    try:
        saved = repository().review_memory_candidate(candidate_id, req.accepted)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Memory candidate not found") from exc
    return {"status": "accepted" if req.accepted else "rejected",
            "memory": serialize(saved) if saved else None}


@router.delete("/{memory_id}", status_code=204)
def delete_memory(memory_id: str) -> Response:
    if not repository().delete_memory(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return Response(status_code=204)


@router.delete("")
def clear_memory(namespace: str = "") -> dict[str, int]:
    return {"deleted": repository().clear_memories(namespace=namespace)}


@router.get("/export")
def export_memory() -> dict[str, Any]:
    return {"version": 1, "items": [serialize(item) for item in repository().list_memories()]}


@router.get("/settings")
def get_memory_settings() -> dict[str, bool]:
    repo = repository()
    return {
        "memory_enabled": bool(repo.get_setting("memory_enabled", True)),
        "cache_enabled": bool(repo.get_setting("cache_enabled", True)),
    }


@router.put("/settings")
def update_memory_settings(req: MemorySettingsRequest) -> dict[str, bool]:
    repo = repository()
    repo.set_setting("memory_enabled", req.memory_enabled)
    repo.set_setting("cache_enabled", req.cache_enabled)
    return req.model_dump()

