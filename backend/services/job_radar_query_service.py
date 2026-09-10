"""Schema-bound, read-only queries over the Job Radar domain model."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.services import job_radar_service


Operation = Literal["count", "distinct_count", "group_by", "search", "get_by_id"]
Metric = Literal["jobs", "companies"]
GroupField = Literal[
    "location", "company", "industry", "company_type", "recruitment_type", "scene", "match_level"
]


class JobRadarFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active"] = "active"
    scene: list[Literal["general", "state_owned", "civil_service"]] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)
    company: list[str] = Field(default_factory=list)
    industry: list[str] = Field(default_factory=list)
    company_type: list[str] = Field(default_factory=list)
    recruitment_type: list[str] = Field(default_factory=list)
    match_level: list[Literal["高匹配", "中匹配", "低匹配"]] = Field(default_factory=list)
    favorite: bool | None = None
    query: str = Field(default="", max_length=200)

    @field_validator("location", "company", "industry", "company_type", "recruitment_type")
    @classmethod
    def normalize_values(cls, values: list[str]) -> list[str]:
        cleaned = [str(value).strip()[:100] for value in values if str(value).strip()]
        return list(dict.fromkeys(cleaned))[:20]

    @field_validator("company_type")
    @classmethod
    def normalize_company_types(cls, values: list[str]) -> list[str]:
        aliases = {"央企": "国企/央企", "国企": "国企/央企", "国有企业": "国企/央企", "事业单位": "科研/事业单位"}
        return list(dict.fromkeys(aliases.get(value, value) for value in values))


class JobRadarSort(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal["count", "score", "last_seen_at"] = "count"
    direction: Literal["asc", "desc"] = "desc"


class JobRadarQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Operation
    metric: Metric = "jobs"
    group_by: GroupField | None = None
    filters: JobRadarFilters = Field(default_factory=JobRadarFilters)
    sort: JobRadarSort = Field(default_factory=JobRadarSort)
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = None
    job_id: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_operation_contract(self) -> "JobRadarQuery":
        if self.operation == "group_by" and not self.group_by:
            raise ValueError("group_by is required for a group_by query")
        if self.operation != "group_by" and self.group_by is not None:
            raise ValueError("group_by is only valid for a group_by query")
        if self.operation == "get_by_id" and not str(self.job_id or "").strip():
            raise ValueError("job_id is required for a get_by_id query")
        if self.operation != "get_by_id" and self.job_id is not None:
            raise ValueError("job_id is only valid for a get_by_id query")
        if self.operation == "distinct_count" and self.metric != "companies":
            raise ValueError("distinct_count currently supports metric=companies only")
        if self.cursor is not None:
            raise ValueError("cursor pagination is not supported in schema version 1")
        if self.operation == "group_by" and self.sort.field != "count":
            raise ValueError("group_by results can only be sorted by count")
        return self


class JobRadarQueryResult(BaseModel):
    schema_version: Literal["1"] = "1"
    operation: Operation
    scope: Literal["database"] = "database"
    metric: Metric
    filters_applied: dict[str, Any]
    value: int | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)
    returned_count: int = 0
    total_count: int = 0
    truncated: bool = False
    as_of: str
    source: Literal["job_radar.sqlite3"] = "job_radar.sqlite3"


def _contains(actual: Any, expected: list[str]) -> bool:
    if not expected:
        return True
    text = str(actual or "").casefold()
    return any(value.casefold() in text for value in expected)


def _domain_rows(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.is_file():
        return []
    profile = job_radar_service.load_user_profile(db_path.parent, db_path)
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute(
            """SELECT p.*, COALESCE(a.favorite, 0) AS favorite,
                      COALESCE(a.not_interested, 0) AS not_interested,
                      COALESCE(a.applied, 0) AS applied
               FROM job_postings p
               LEFT JOIN job_radar_actions a ON a.job_id=p.id
               WHERE p.status=?""",
            ("active",),
        ).fetchall()]
    for row in rows:
        row["favorite"] = bool(row["favorite"])
        row["company_type"] = job_radar_service._company_type(row)
        score = job_radar_service.score_job(row, profile)["score"]
        row["score"] = score
        row["match_level"] = job_radar_service._match_level(score)
    return rows


def _filtered_rows(rows: list[dict[str, Any]], filters: JobRadarFilters) -> list[dict[str, Any]]:
    query = filters.query.casefold().strip()
    result = []
    for row in rows:
        if filters.scene and row.get("scene") not in filters.scene:
            continue
        if not _contains(row.get("location"), filters.location):
            continue
        if not _contains(row.get("company"), filters.company):
            continue
        if not _contains(row.get("industry"), filters.industry):
            continue
        if filters.company_type and row.get("company_type") not in filters.company_type:
            continue
        if not _contains(row.get("recruitment_type"), filters.recruitment_type):
            continue
        if filters.match_level and row.get("match_level") not in filters.match_level:
            continue
        if filters.favorite is not None and row.get("favorite") is not filters.favorite:
            continue
        if query and query not in " ".join(
            str(row.get(field) or "").casefold()
            for field in ("company", "role", "location", "industry", "recruitment_type", "description")
        ):
            continue
        result.append(row)
    return result


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "id", "company", "role", "location", "industry", "company_type", "recruitment_type",
        "scene", "match_level", "score", "favorite", "deadline", "link", "last_seen_at",
    )
    return {field: row.get(field) for field in fields}


def execute_job_radar_query(
    payload: JobRadarQuery | dict[str, Any], db_path: Path = job_radar_service.DB_PATH,
) -> dict[str, Any]:
    query = payload if isinstance(payload, JobRadarQuery) else JobRadarQuery.model_validate(payload)

    filtered = _filtered_rows(_domain_rows(db_path), query.filters)
    rows: list[dict[str, Any]] = []
    value: int | None = None
    total_count = 0

    if query.operation == "count":
        value = len(filtered) if query.metric == "jobs" else len({row["company"] for row in filtered if row["company"]})
        total_count = value
    elif query.operation == "distinct_count":
        value = len({row["company"] for row in filtered if row["company"]})
        total_count = value
    elif query.operation == "group_by":
        grouped: dict[str, set[str] | int] = {}
        for row in filtered:
            key = str(row.get(query.group_by or "") or "未标注")
            if query.metric == "companies":
                grouped.setdefault(key, set())
                assert isinstance(grouped[key], set)
                if row.get("company"):
                    grouped[key].add(str(row["company"]))
            else:
                grouped[key] = int(grouped.get(key, 0)) + 1
        counts = Counter({key: len(value_) if isinstance(value_, set) else value_ for key, value_ in grouped.items()})
        ordered = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=query.sort.direction == "desc")
        total_count = len(ordered)
        rows = [{"key": key, "count": count} for key, count in ordered[:query.limit]]
    elif query.operation == "get_by_id":
        matched = [row for row in filtered if str(row.get("id")) == query.job_id]
        total_count = len(matched)
        rows = [_public_row(row) for row in matched[:1]]
    else:
        reverse = query.sort.direction == "desc"
        sort_field = query.sort.field if query.sort.field in {"score", "last_seen_at"} else "score"
        ordered = sorted(filtered, key=lambda row: (row.get(sort_field) or 0, row.get("id") or ""), reverse=reverse)
        total_count = len(ordered)
        rows = [_public_row(row) for row in ordered[:query.limit]]

    filters_applied = query.filters.model_dump(exclude_none=True)
    return JobRadarQueryResult(
        operation=query.operation,
        metric=query.metric,
        filters_applied=filters_applied,
        value=value,
        rows=rows,
        returned_count=len(rows),
        total_count=total_count,
        truncated=bool(rows and total_count > len(rows)),
        as_of=datetime.now(timezone.utc).isoformat(),
    ).model_dump()
