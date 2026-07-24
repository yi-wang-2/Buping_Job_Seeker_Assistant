from __future__ import annotations

import json
import sqlite3
from collections import OrderedDict
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from ..models import LLMResponse, TokenUsage
from .fingerprints import document_fingerprint


class PromptCache:
    def __init__(self, path: str | Path = "data_folder/ai_memory.sqlite3", max_items: int = 128) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_items = max_items
        self._memory: OrderedDict[str, LLMResponse] = OrderedDict()
        self._lock = Lock()
        self._ensure_schema()

    @staticmethod
    def key(*, provider: str, model: str, skill: str, skill_version: str, messages: Any, parameters: Any, schema_version: str = "1") -> str:
        return document_fingerprint({
            "provider": provider, "model": model, "skill": skill,
            "skill_version": skill_version, "messages": messages,
            "parameters": parameters, "schema_version": schema_version,
        })

    def get(self, key: str) -> LLMResponse | None:
        with self._lock:
            if key in self._memory:
                response = self._memory.pop(key)
                self._memory[key] = response
                self._increment_hit(key)
                return response
        if not self.path.exists():
            return None
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            row = db.execute(
                "SELECT response_json, expires_at FROM prompt_cache WHERE cache_key=?", (key,)
            ).fetchone()
            if not row:
                return None
            if row[1] and datetime.fromisoformat(row[1]) <= datetime.now(timezone.utc):
                db.execute("DELETE FROM prompt_cache WHERE cache_key=?", (key,))
                db.commit()
                return None
            db.execute("UPDATE prompt_cache SET hit_count=hit_count+1 WHERE cache_key=?", (key,))
            db.commit()
        response = self._decode(row[0])
        self._remember(key, response)
        return response

    def stats(self) -> dict[str, int]:
        if not self.path.exists():
            return {"entries": 0, "hits": 0}
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            row = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM prompt_cache"
            ).fetchone()
        return {"entries": int(row[0]), "hits": int(row[1])}

    def put(self, key: str, response: LLMResponse, ttl_seconds: int = 86400) -> None:
        self._remember(key, response)
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute("""
                INSERT INTO prompt_cache(cache_key,response_json,created_at,expires_at,hit_count)
                VALUES (?,?,?,?,0) ON CONFLICT(cache_key) DO UPDATE SET
                response_json=excluded.response_json, created_at=excluded.created_at,
                expires_at=excluded.expires_at
            """, (key, json.dumps(asdict(response), ensure_ascii=False), datetime.now(timezone.utc).isoformat(), expires.isoformat()))
            db.commit()

    def _remember(self, key: str, response: LLMResponse) -> None:
        with self._lock:
            self._memory.pop(key, None)
            self._memory[key] = response
            while len(self._memory) > self.max_items:
                self._memory.popitem(last=False)

    def _increment_hit(self, key: str) -> None:
        if not self.path.exists():
            return
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute("UPDATE prompt_cache SET hit_count=hit_count+1 WHERE cache_key=?", (key,))
            db.commit()

    def _ensure_schema(self) -> None:
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS prompt_cache (
                    cache_key TEXT PRIMARY KEY, response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, expires_at TEXT,
                    hit_count INTEGER NOT NULL DEFAULT 0
                )
            """)
            db.commit()

    @staticmethod
    def _decode(raw: str) -> LLMResponse:
        data = json.loads(raw)
        data["usage"] = TokenUsage(**data.get("usage", {}))
        return LLMResponse(**data)
