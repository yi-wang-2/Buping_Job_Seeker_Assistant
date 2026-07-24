from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .models import MemoryItem


SCHEMA_VERSION = 1


class SQLiteMemoryRepository:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.getenv("AI_MEMORY_DB", "data_folder/ai_memory.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def migrate(self) -> None:
        with self.connection() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_items (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, namespace TEXT NOT NULL,
                    key TEXT NOT NULL, value_json TEXT NOT NULL, source TEXT NOT NULL,
                    confidence REAL NOT NULL, importance INTEGER NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, expires_at TEXT,
                    content_hash TEXT NOT NULL,
                    UNIQUE(user_id, namespace, key), FOREIGN KEY(user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS memory_events (
                    id TEXT PRIMARY KEY, memory_id TEXT, operation TEXT NOT NULL,
                    payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS job_descriptions (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, company TEXT, role TEXT,
                    raw_text TEXT NOT NULL, normalized_json TEXT NOT NULL, source_url TEXT,
                    content_hash TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, last_used_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS resume_versions (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, parent_version_id TEXT,
                    language TEXT NOT NULL, content TEXT NOT NULL, content_hash TEXT NOT NULL,
                    change_summary TEXT, source_skill_run_id TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS interview_sessions (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, summary TEXT,
                    metadata_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS interview_messages (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL,
                    content TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skill_runs (
                    id TEXT PRIMARY KEY, skill_name TEXT NOT NULL, skill_version TEXT NOT NULL,
                    user_id TEXT NOT NULL, session_id TEXT, input_hash TEXT NOT NULL, model TEXT,
                    usage_json TEXT NOT NULL, cache_hit INTEGER NOT NULL, status TEXT NOT NULL,
                    error_code TEXT, started_at TEXT NOT NULL, finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS prompt_cache (
                    cache_key TEXT PRIMARY KEY, response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, expires_at TEXT, hit_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS ai_settings (
                    key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL
                );
            """)
            db.execute("INSERT OR IGNORE INTO users(id, created_at) VALUES (?, ?)", ("local", self._now()))
            db.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, self._now()),
            )

    def upsert_memory(self, item: MemoryItem) -> MemoryItem:
        now = self._now()
        memory_id = item.id or str(uuid.uuid4())
        value_json = self._json(item.value)
        content_hash = hashlib.sha256(value_json.encode("utf-8")).hexdigest()
        with self.connection() as db:
            existing = db.execute(
                "SELECT id, created_at FROM memory_items WHERE user_id=? AND namespace=? AND key=?",
                (item.user_id, item.namespace, item.key),
            ).fetchone()
            if existing:
                memory_id = existing["id"]
            db.execute("""
                INSERT INTO memory_items(
                    id,user_id,namespace,key,value_json,source,confidence,importance,status,
                    created_at,updated_at,expires_at,content_hash
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id,namespace,key) DO UPDATE SET
                    value_json=excluded.value_json, source=excluded.source,
                    confidence=excluded.confidence, importance=excluded.importance,
                    status=excluded.status, updated_at=excluded.updated_at,
                    expires_at=excluded.expires_at, content_hash=excluded.content_hash
            """, (
                memory_id, item.user_id, item.namespace, item.key, value_json, item.source,
                item.confidence, item.importance, item.status,
                existing["created_at"] if existing else now, now,
                item.expires_at.isoformat() if item.expires_at else None, content_hash,
            ))
            db.execute(
                "INSERT INTO memory_events VALUES (?,?,?,?,?)",
                (str(uuid.uuid4()), memory_id, "UPDATE" if existing else "ADD", value_json, now),
            )
        return self.get_memory(memory_id)

    def get_memory(self, memory_id: str) -> MemoryItem:
        with self.connection() as db:
            row = db.execute("SELECT * FROM memory_items WHERE id=?", (memory_id,)).fetchone()
        if not row:
            raise KeyError(memory_id)
        return self._row_to_memory(row)

    def list_memories(self, user_id: str = "local", namespace: str = "") -> list[MemoryItem]:
        query = "SELECT * FROM memory_items WHERE user_id=? AND status='active'"
        args: list[Any] = [user_id]
        if namespace:
            query += " AND namespace=?"
            args.append(namespace)
        query += " ORDER BY importance DESC, updated_at DESC"
        with self.connection() as db:
            rows = db.execute(query, args).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def delete_memory(self, memory_id: str) -> bool:
        with self.connection() as db:
            result = db.execute("DELETE FROM memory_items WHERE id=?", (memory_id,))
            if result.rowcount:
                db.execute("INSERT INTO memory_events VALUES (?,?,?,?,?)", (str(uuid.uuid4()), memory_id, "DELETE", "{}", self._now()))
        return bool(result.rowcount)

    def clear_memories(self, user_id: str = "local", namespace: str = "") -> int:
        query = "DELETE FROM memory_items WHERE user_id=?"
        args: list[Any] = [user_id]
        if namespace:
            query += " AND namespace=?"
            args.append(namespace)
        with self.connection() as db:
            result = db.execute(query, args)
        return result.rowcount

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connection() as db:
            row = db.execute("SELECT value_json FROM ai_settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value_json"]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self.connection() as db:
            db.execute("""
                INSERT INTO ai_settings(key,value_json,updated_at) VALUES (?,?,?)
                ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at
            """, (key, self._json(value), self._now()))

    def archive_job_description(
        self,
        raw_text: str,
        normalized: dict[str, Any],
        *,
        user_id: str = "local",
        company: str = "",
        role: str = "",
        source_url: str = "",
    ) -> dict[str, Any]:
        """Insert or refresh a deduplicated JD archive entry."""
        normalized_json = self._json(normalized)
        content_hash = hashlib.sha256(raw_text.strip().encode("utf-8")).hexdigest()
        now = self._now()
        with self.connection() as db:
            existing = db.execute(
                "SELECT id, created_at FROM job_descriptions WHERE content_hash=?",
                (content_hash,),
            ).fetchone()
            job_id = existing["id"] if existing else str(uuid.uuid4())
            db.execute("""
                INSERT INTO job_descriptions(
                    id,user_id,company,role,raw_text,normalized_json,source_url,
                    content_hash,status,created_at,last_used_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(content_hash) DO UPDATE SET
                    normalized_json=excluded.normalized_json,
                    company=excluded.company, role=excluded.role,
                    source_url=excluded.source_url, last_used_at=excluded.last_used_at,
                    status='active'
            """, (
                job_id, user_id, company, role, raw_text, normalized_json,
                source_url, content_hash, "active",
                existing["created_at"] if existing else now, now,
            ))
        return {
            "id": job_id,
            "content_hash": content_hash,
            "deduplicated": bool(existing),
            "last_used_at": now,
        }

    def list_job_descriptions(self, user_id: str = "local", limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("""
                SELECT id,company,role,normalized_json,source_url,content_hash,
                       status,created_at,last_used_at
                FROM job_descriptions WHERE user_id=? AND status='active'
                ORDER BY last_used_at DESC LIMIT ?
            """, (user_id, max(1, min(limit, 500)))).fetchall()
        return [
            {
                "id": row["id"], "company": row["company"] or "",
                "role": row["role"] or "", "analysis": json.loads(row["normalized_json"]),
                "source_url": row["source_url"] or "", "content_hash": row["content_hash"],
                "status": row["status"], "created_at": row["created_at"],
                "last_used_at": row["last_used_at"],
            }
            for row in rows
        ]

    def record_skill_run(
        self,
        *,
        skill_name: str,
        skill_version: str,
        input_hash: str,
        model: str,
        usage: dict[str, int],
        cache_hit: bool,
        status: str = "success",
        error_code: str = "",
        user_id: str = "local",
        session_id: str = "",
    ) -> str:
        run_id = str(uuid.uuid4())
        now = self._now()
        with self.connection() as db:
            db.execute("""
                INSERT INTO skill_runs(
                    id,skill_name,skill_version,user_id,session_id,input_hash,model,
                    usage_json,cache_hit,status,error_code,started_at,finished_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                run_id, skill_name, skill_version, user_id, session_id or None,
                input_hash, model, self._json(usage), int(cache_hit), status,
                error_code or None, now, now,
            ))
        return run_id

    def save_resume_version(
        self,
        content: str,
        *,
        language: str = "zh",
        change_summary: str = "",
        source_skill_run_id: str = "",
        user_id: str = "local",
    ) -> dict[str, Any]:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        now = self._now()
        with self.connection() as db:
            latest = db.execute("""
                SELECT id,content_hash FROM resume_versions
                WHERE user_id=? AND language=? ORDER BY created_at DESC LIMIT 1
            """, (user_id, language)).fetchone()
            if latest and latest["content_hash"] == content_hash:
                return {"id": latest["id"], "content_hash": content_hash, "deduplicated": True}
            version_id = str(uuid.uuid4())
            db.execute("""
                INSERT INTO resume_versions(
                    id,user_id,parent_version_id,language,content,content_hash,
                    change_summary,source_skill_run_id,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                version_id, user_id, latest["id"] if latest else None,
                language, content, content_hash, change_summary,
                source_skill_run_id or None, now,
            ))
        return {"id": version_id, "content_hash": content_hash, "deduplicated": False}

    def list_resume_versions(self, language: str = "zh", user_id: str = "local", limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("""
                SELECT id,parent_version_id,language,content_hash,change_summary,
                       source_skill_run_id,created_at,LENGTH(content) AS content_length
                FROM resume_versions WHERE user_id=? AND language=?
                ORDER BY created_at DESC LIMIT ?
            """, (user_id, language, max(1, min(limit, 500)))).fetchall()
        return [dict(row) for row in rows]

    def get_resume_version(self, version_id: str, user_id: str = "local") -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("""
                SELECT id,parent_version_id,language,content,content_hash,
                       change_summary,source_skill_run_id,created_at
                FROM resume_versions WHERE id=? AND user_id=?
            """, (version_id, user_id)).fetchone()
        if not row:
            raise KeyError(version_id)
        return dict(row)

    @staticmethod
    def _row_to_memory(row: sqlite3.Row) -> MemoryItem:
        return MemoryItem(
            id=row["id"], user_id=row["user_id"], namespace=row["namespace"], key=row["key"],
            value=json.loads(row["value_json"]), source=row["source"], confidence=row["confidence"],
            importance=row["importance"], status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
        )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

