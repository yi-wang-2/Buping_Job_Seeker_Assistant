"""Aggregate local AI runtime metrics for the monitoring dashboard."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_USAGE_PATH = ROOT / "data_folder" / "output" / "ai_usage.jsonl"
DEFAULT_DB_PATH = ROOT / "data_folder" / "ai_memory.sqlite3"
DEFAULT_KNOWLEDGE_DB_PATH = ROOT / "data_folder" / "interview_knowledge.sqlite3"


def _load_events(path: Path = DEFAULT_USAGE_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                event = json.loads(line)
                event["_timestamp"] = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                events.append(event)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return events


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _database_metrics(path: Path = DEFAULT_DB_PATH) -> dict[str, int]:
    result = {"cache_entries": 0, "cache_hits": 0, "cache_saved_tokens": 0, "memory_items": 0, "skill_runs": 0}
    if not path.exists():
        return result
    try:
        with sqlite3.connect(path, timeout=3) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "prompt_cache" in tables:
                row = db.execute("SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM prompt_cache").fetchone()
                result.update(cache_entries=int(row[0]), cache_hits=int(row[1]))
                for response_json, hit_count in db.execute("SELECT response_json, hit_count FROM prompt_cache"):
                    try:
                        payload = json.loads(response_json or "{}")
                        usage = payload.get("usage") or {}
                        original_tokens = int(usage.get("total_tokens", 0))
                        result["cache_saved_tokens"] += original_tokens * int(hit_count or 0)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        continue
            if "memory_items" in tables:
                result["memory_items"] = int(db.execute("SELECT COUNT(*) FROM memory_items WHERE status='active'").fetchone()[0])
            if "skill_runs" in tables:
                result["skill_runs"] = int(db.execute("SELECT COUNT(*) FROM skill_runs").fetchone()[0])
    except sqlite3.Error:
        pass
    return result


def _knowledge_database_metrics(path: Path = DEFAULT_KNOWLEDGE_DB_PATH) -> dict[str, int]:
    result = {"sources": 0, "active_sources": 0, "units": 0}
    if not path.exists():
        return result
    try:
        with sqlite3.connect(path, timeout=3) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "knowledge_sources" in tables:
                row = db.execute(
                    "SELECT COUNT(*), COALESCE(SUM(sync_status='ready'),0) FROM knowledge_sources"
                ).fetchone()
                result.update(sources=int(row[0]), active_sources=int(row[1]))
            if "knowledge_units" in tables:
                result["units"] = int(db.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()[0])
    except sqlite3.Error:
        pass
    return result


def _assistant_metrics(path: Path, cutoff: datetime) -> dict[str, Any]:
    empty = {
        "summary": {"runs": 0, "completed": 0, "failed": 0, "cancelled": 0,
                    "active": 0, "total_tokens": 0, "avg_latency_ms": 0},
        "by_mode": [], "by_page": [], "recent": [],
    }
    if not path.exists():
        return empty
    try:
        with sqlite3.connect(path, timeout=3) as db:
            db.row_factory = sqlite3.Row
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "assistant_runs" not in tables:
                return empty
            rows = [dict(row) for row in db.execute(
                "SELECT id, page, proposed_mode, effective_mode, intent, dispatch_path, usage_json, "
                "status, error_code, started_at, finished_at FROM assistant_runs ORDER BY started_at DESC"
            ).fetchall()]
    except sqlite3.Error:
        return empty

    filtered: list[dict[str, Any]] = []
    for row in rows:
        try:
            started = datetime.fromisoformat(str(row["started_at"]).replace("Z", "+00:00"))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if started < cutoff:
                continue
        except (TypeError, ValueError):
            continue
        try:
            usage = json.loads(row.pop("usage_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            usage = {}
        row["usage"] = usage
        row["total_tokens"] = int(usage.get("total_tokens", 0))
        row["latency_ms"] = 0
        if row.get("finished_at"):
            try:
                finished = datetime.fromisoformat(str(row["finished_at"]).replace("Z", "+00:00"))
                if finished.tzinfo is None:
                    finished = finished.replace(tzinfo=timezone.utc)
                row["latency_ms"] = max(0, round((finished - started).total_seconds() * 1000))
            except (TypeError, ValueError):
                pass
        filtered.append(row)

    grouped_mode: dict[str, dict[str, int]] = defaultdict(lambda: {"runs": 0, "tokens": 0, "failures": 0})
    grouped_page: dict[str, dict[str, int]] = defaultdict(lambda: {"runs": 0, "tokens": 0, "failures": 0})
    for row in filtered:
        mode = row.get("effective_mode") or row.get("proposed_mode") or "pending"
        page = row.get("page") or "unknown"
        for target in (grouped_mode[mode], grouped_page[page]):
            target["runs"] += 1
            target["tokens"] += row["total_tokens"]
            target["failures"] += int(row.get("status") == "failed")
    terminal_latencies = [row["latency_ms"] for row in filtered if row["latency_ms"] > 0]
    statuses = defaultdict(int)
    for row in filtered:
        statuses[str(row.get("status") or "unknown")] += 1
    return {
        "summary": {
            "runs": len(filtered), "completed": statuses["completed"], "failed": statuses["failed"],
            "cancelled": statuses["cancelled"],
            "active": statuses["running"] + statuses["cancel_requested"],
            "total_tokens": sum(row["total_tokens"] for row in filtered),
            "avg_latency_ms": round(sum(terminal_latencies) / len(terminal_latencies)) if terminal_latencies else 0,
        },
        "by_mode": [{"mode": key, **value} for key, value in sorted(grouped_mode.items())],
        "by_page": [{"page": key, **value} for key, value in sorted(grouped_page.items())],
        "recent": filtered[:30],
    }


def get_ai_metrics(
    days: int = 30, usage_path: Path = DEFAULT_USAGE_PATH, db_path: Path = DEFAULT_DB_PATH,
    knowledge_db_path: Path = DEFAULT_KNOWLEDGE_DB_PATH,
) -> dict[str, Any]:
    days = max(1, min(days, 365))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    events = [event for event in _load_events(usage_path) if event["_timestamp"] >= cutoff]
    database = _database_metrics(db_path)
    successful = [event for event in events if event.get("status") == "success"]
    latencies = [int(event.get("latency_ms", 0)) for event in successful]
    totals = defaultdict(int)
    by_skill: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "tokens": 0, "errors": 0, "latency_total_ms": 0})
    by_model: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "tokens": 0})
    by_day: dict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "tokens": 0, "errors": 0})
    context_original = context_final = compressed_items = dropped_items = 0
    retrieval_calls = units_retrieved = knowledge_candidates = 0
    retrieval_latency = 0.0
    knowledge_sources: dict[str, int] = defaultdict(int)

    for event in events:
        usage = event.get("usage") or {}
        input_tokens = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens))
        totals["input_tokens"] += input_tokens
        totals["output_tokens"] += output_tokens
        totals["total_tokens"] += total_tokens
        totals["retries"] += int(event.get("retries", 0))
        skill = event.get("skill") or "unknown"
        model = event.get("model") or "unknown"
        day = event["_timestamp"].date().isoformat()
        for target in (by_skill[skill], by_model[model], by_day[day]):
            target["calls"] += 1
            target["tokens"] += total_tokens
        by_skill[skill]["latency_total_ms"] += int(event.get("latency_ms", 0))
        if event.get("status") != "success":
            by_skill[skill]["errors"] += 1
            by_day[day]["errors"] += 1
        context = event.get("context") or {}
        context_original += int(context.get("original_tokens", 0))
        context_final += int(context.get("final_tokens", 0))
        compressed_items += int(context.get("items_compressed", 0))
        dropped_items += int(context.get("items_dropped", 0))
        knowledge = event.get("knowledge") or {}
        unit_ids = list(knowledge.get("unit_ids") or [])
        if unit_ids:
            retrieval_calls += 1
            units_retrieved += len(unit_ids)
            knowledge_candidates += int(knowledge.get("candidates", 0))
            retrieval_latency += float(knowledge.get("retrieval_ms", 0))
            for source_id in knowledge.get("source_ids") or []:
                knowledge_sources[str(source_id)] += 1

    skill_rows = []
    for skill, values in sorted(by_skill.items(), key=lambda item: item[1]["tokens"], reverse=True):
        calls = values["calls"]
        skill_rows.append({
            "skill": skill, "calls": calls, "tokens": values["tokens"], "errors": values["errors"],
            "avg_latency_ms": round(values["latency_total_ms"] / calls) if calls else 0,
        })
    calls = len(events)
    cache_denominator = database["cache_hits"] + calls
    knowledge_db = _knowledge_database_metrics(knowledge_db_path)
    return {
        "period_days": days,
        "summary": {
            "calls": calls,
            "successful_calls": len(successful),
            "errors": calls - len(successful),
            "success_rate": round(len(successful) / calls * 100, 2) if calls else 0,
            **totals,
            "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
            "p95_latency_ms": _percentile(latencies, 0.95),
            "cache_hits": database["cache_hits"],
            "cache_saved_tokens": database["cache_saved_tokens"],
            "cache_entries": database["cache_entries"],
            "cache_hit_rate": round(database["cache_hits"] / cache_denominator * 100, 2) if cache_denominator else 0,
            "memory_items": database["memory_items"],
            "context_original_tokens": context_original,
            "context_final_tokens": context_final,
            "context_saved_tokens": max(0, context_original - context_final),
            "context_compression_rate": round((1 - context_final / context_original) * 100, 2) if context_original else 0,
            "compressed_items": compressed_items,
            "dropped_items": dropped_items,
        },
        "by_skill": skill_rows,
        "by_model": [{"model": key, **value} for key, value in sorted(by_model.items(), key=lambda item: item[1]["tokens"], reverse=True)],
        "timeline": [{"date": key, **value} for key, value in sorted(by_day.items())],
        "recent": [
            {key: value for key, value in event.items() if key != "_timestamp"}
            for event in sorted(events, key=lambda item: item["_timestamp"], reverse=True)[:50]
        ],
        "assistant": _assistant_metrics(db_path, cutoff),
        "knowledge": {
            **knowledge_db, "retrieval_calls": retrieval_calls,
            "units_retrieved": units_retrieved, "candidates": knowledge_candidates,
            "avg_retrieval_ms": round(retrieval_latency / retrieval_calls, 2) if retrieval_calls else 0,
            "by_source": [
                {"source_id": key, "uses": value}
                for key, value in sorted(knowledge_sources.items(), key=lambda item: item[1], reverse=True)
            ],
        },
    }
