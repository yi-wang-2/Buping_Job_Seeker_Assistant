import json
import sqlite3
from datetime import datetime, timezone

from backend.services.ai_metrics_service import get_ai_metrics
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
