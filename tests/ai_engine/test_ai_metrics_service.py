import json
import sqlite3
from datetime import datetime, timezone

from backend.services.ai_metrics_service import get_ai_metrics
from backend.services.assistant_repository import AssistantRepository
from src.libs.ai_engine.memory import SQLiteMemoryRepository


def test_ai_metrics_aggregates_usage_cache_and_memory(tmp_path):
    usage_path = tmp_path / "usage.jsonl"
    usage_path.write_text(json.dumps({
        "trace_id": "1", "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": "fake", "model": "fake-model", "skill": "text_rewriter",
        "status": "success", "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        "latency_ms": 20, "retries": 0,
        "context": {"original_tokens": 20, "final_tokens": 12, "items_compressed": 1, "items_dropped": 0},
    }) + "\n", encoding="utf-8")
    db_path = tmp_path / "memory.sqlite3"
    SQLiteMemoryRepository(db_path)
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO prompt_cache VALUES (?,?,?,?,?)", ("key", "{}", datetime.now(timezone.utc).isoformat(), None, 3))
        db.commit()

    metrics = get_ai_metrics(30, usage_path, db_path)

    assert metrics["summary"]["total_tokens"] == 15
    assert metrics["summary"]["cache_hits"] == 3
    assert metrics["summary"]["context_saved_tokens"] == 8
    assert metrics["by_skill"][0]["skill"] == "text_rewriter"
    assert metrics["assistant"]["summary"]["runs"] == 0


def test_ai_metrics_aggregates_end_to_end_assistant_runs(tmp_path):
    usage_path = tmp_path / "usage.jsonl"
    usage_path.write_text("", encoding="utf-8")
    db_path = tmp_path / "memory.sqlite3"
    repository = AssistantRepository(db_path)
    session = repository.get_or_create_session("resume", "metrics")
    run = repository.create_run(session["id"], "resume")
    repository.finish_run(
        run["id"], mode="direct_skill", intent="review", dispatch_path="supervisor",
        policy={"allowed": True}, usage={"total_tokens": 42},
    )

    metrics = get_ai_metrics(30, usage_path, db_path)

    assert metrics["assistant"]["summary"]["runs"] == 1
    assert metrics["assistant"]["summary"]["total_tokens"] == 42
    assert metrics["assistant"]["by_mode"][0]["mode"] == "direct_skill"
