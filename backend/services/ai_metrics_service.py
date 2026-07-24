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
    result = {"cache_entries": 0, "cache_hits": 0, "memory_items": 0, "skill_runs": 0}
    if not path.exists():
        return result
    try:
        with sqlite3.connect(path, timeout=3) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "prompt_cache" in tables:
                row = db.execute("SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM prompt_cache").fetchone()
                result.update(cache_entries=int(row[0]), cache_hits=int(row[1]))
            if "memory_items" in tables:
                result["memory_items"] = int(db.execute("SELECT COUNT(*) FROM memory_items WHERE status='active'").fetchone()[0])
            if "skill_runs" in tables:
                result["skill_runs"] = int(db.execute("SELECT COUNT(*) FROM skill_runs").fetchone()[0])
    except sqlite3.Error:
        pass
    return result


def get_ai_metrics(days: int = 30, usage_path: Path = DEFAULT_USAGE_PATH, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
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

    skill_rows = []
    for skill, values in sorted(by_skill.items(), key=lambda item: item[1]["tokens"], reverse=True):
        calls = values["calls"]
        skill_rows.append({
            "skill": skill, "calls": calls, "tokens": values["tokens"], "errors": values["errors"],
            "avg_latency_ms": round(values["latency_total_ms"] / calls) if calls else 0,
        })
    calls = len(events)
    cache_denominator = database["cache_hits"] + calls
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
    }

