from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.libs.ai_engine.memory import SQLiteMemoryRepository


class AssistantRepository:
    """Assistant-owned tables sharing the existing privacy-first SQLite file."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.memory = SQLiteMemoryRepository(path)
        self.migrate()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _row(row: Any) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def migrate(self) -> None:
        with self.memory.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS assistant_sessions (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, workspace_type TEXT NOT NULL,
                    workspace_object_id TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(user_id, workspace_type, workspace_object_id)
                );
                CREATE TABLE IF NOT EXISTS assistant_messages (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL,
                    content TEXT NOT NULL, run_id TEXT, status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES assistant_sessions(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS assistant_runs (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, page TEXT NOT NULL,
                    proposed_mode TEXT, effective_mode TEXT, intent TEXT NOT NULL,
                    dispatch_path TEXT NOT NULL, policy_decision_json TEXT NOT NULL,
                    budget_json TEXT NOT NULL, usage_json TEXT NOT NULL, status TEXT NOT NULL,
                    error_code TEXT, started_at TEXT NOT NULL, finished_at TEXT,
                    FOREIGN KEY(session_id) REFERENCES assistant_sessions(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS assistant_steps (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, step_index INTEGER NOT NULL,
                    skill_name TEXT, action_name TEXT, input_fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL, usage_json TEXT NOT NULL, observation_json TEXT NOT NULL,
                    started_at TEXT NOT NULL, finished_at TEXT,
                    FOREIGN KEY(run_id) REFERENCES assistant_runs(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS assistant_proposals (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, proposal_type TEXT NOT NULL,
                    target_ref TEXT NOT NULL, target_version TEXT NOT NULL, payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, risk TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, applied_at TEXT,
                    FOREIGN KEY(run_id) REFERENCES assistant_runs(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS assistant_attachments (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, filename TEXT NOT NULL,
                    mime_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, content_text TEXT NOT NULL,
                    content_hash TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES assistant_sessions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_assistant_messages_session
                    ON assistant_messages(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_assistant_runs_session
                    ON assistant_runs(session_id, started_at);
                CREATE INDEX IF NOT EXISTS idx_assistant_attachments_session
                    ON assistant_attachments(session_id, created_at);
            """)
            proposal_columns = {row[1] for row in db.execute("PRAGMA table_info(assistant_proposals)")}
            if "confirmation_token_hash" not in proposal_columns:
                db.execute("ALTER TABLE assistant_proposals ADD COLUMN confirmation_token_hash TEXT")
            if "confirmation_expires_at" not in proposal_columns:
                db.execute("ALTER TABLE assistant_proposals ADD COLUMN confirmation_expires_at TEXT")

    def get_or_create_session(self, workspace_type: str, workspace_object_id: str = "default",
                              *, user_id: str = "local", title: str = "") -> dict[str, Any]:
        with self.memory.connection() as db:
            row = db.execute(
                "SELECT * FROM assistant_sessions WHERE user_id=? AND workspace_type=? AND workspace_object_id=?",
                (user_id, workspace_type, workspace_object_id),
            ).fetchone()
            if row:
                return dict(row)
            now = self._now()
            session_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO assistant_sessions VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
                (session_id, user_id, workspace_type, workspace_object_id,
                 title or f"{workspace_type} assistant", now, now),
            )
            row = db.execute("SELECT * FROM assistant_sessions WHERE id=?", (session_id,)).fetchone()
            return dict(row)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self.memory.connection() as db:
            return self._row(db.execute("SELECT * FROM assistant_sessions WHERE id=?", (session_id,)).fetchone())

    def list_active_runs(self, session_id: str) -> list[dict[str, Any]]:
        with self.memory.connection() as db:
            rows = db.execute(
                "SELECT * FROM assistant_runs WHERE session_id=? AND status IN ('running','cancel_requested') "
                "ORDER BY started_at DESC",
                (session_id,),
            ).fetchall()
        return [self._decode_run(dict(row)) for row in rows]

    def add_message(self, session_id: str, role: str, content: str, *, run_id: str = "",
                    status: str = "completed", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        message_id, now = str(uuid.uuid4()), self._now()
        with self.memory.connection() as db:
            db.execute(
                "INSERT INTO assistant_messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (message_id, session_id, role, content, run_id or None, status,
                 self._json(metadata or {}), now),
            )
            db.execute("UPDATE assistant_sessions SET updated_at=? WHERE id=?", (now, session_id))
        return {"id": message_id, "session_id": session_id, "role": role, "content": content,
                "run_id": run_id or None, "status": status, "metadata": metadata or {}, "created_at": now}

    def list_messages(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.memory.connection() as db:
            rows = db.execute(
                "SELECT * FROM assistant_messages WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        items = []
        for row in reversed(rows):
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            items.append(item)
        return items

    def create_attachment(
        self, session_id: str, *, filename: str, mime_type: str, size_bytes: int,
        content_text: str,
    ) -> dict[str, Any]:
        attachment_id, now = str(uuid.uuid4()), self._now()
        content_hash = hashlib.sha256(content_text.encode("utf-8")).hexdigest()
        with self.memory.connection() as db:
            db.execute(
                "INSERT INTO assistant_attachments VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (attachment_id, session_id, filename, mime_type, size_bytes, content_text,
                 content_hash, now),
            )
        return {
            "id": attachment_id, "session_id": session_id, "filename": filename,
            "mime_type": mime_type, "size_bytes": size_bytes,
            "character_count": len(content_text), "content_hash": content_hash,
            "created_at": now,
        }

    def list_attachments(self, session_id: str) -> list[dict[str, Any]]:
        with self.memory.connection() as db:
            rows = db.execute(
                "SELECT id, session_id, filename, mime_type, size_bytes, length(content_text) "
                "AS character_count, content_hash, created_at FROM assistant_attachments "
                "WHERE session_id=? ORDER BY created_at",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_attachments(self, session_id: str, attachment_ids: list[str]) -> list[dict[str, Any]]:
        if not attachment_ids:
            return []
        placeholders = ",".join("?" for _ in attachment_ids)
        with self.memory.connection() as db:
            rows = db.execute(
                f"SELECT * FROM assistant_attachments WHERE session_id=? AND id IN ({placeholders})",
                (session_id, *attachment_ids),
            ).fetchall()
        by_id = {row["id"]: dict(row) for row in rows}
        return [by_id[item] for item in attachment_ids if item in by_id]

    def create_run(self, session_id: str, page: str) -> dict[str, Any]:
        run_id, now = str(uuid.uuid4()), self._now()
        with self.memory.connection() as db:
            db.execute(
                "INSERT INTO assistant_runs VALUES (?, ?, ?, NULL, NULL, '', '', '{}', '{}', '{}', 'running', NULL, ?, NULL)",
                (run_id, session_id, page, now),
            )
        return {"id": run_id, "session_id": session_id, "page": page, "status": "running",
                "started_at": now}

    def finish_run(self, run_id: str, *, mode: str, intent: str, dispatch_path: str,
                   policy: dict[str, Any], usage: dict[str, Any] | None = None,
                   status: str = "completed", error_code: str = "") -> dict[str, Any]:
        now = self._now()
        with self.memory.connection() as db:
            db.execute(
                "UPDATE assistant_runs SET proposed_mode=?, effective_mode=?, intent=?, dispatch_path=?, "
                "policy_decision_json=?, usage_json=?, status=?, error_code=?, finished_at=? WHERE id=?",
                (mode, mode, intent, dispatch_path, self._json(policy), self._json(usage or {}),
                 status, error_code or None, now, run_id),
            )
            row = db.execute("SELECT * FROM assistant_runs WHERE id=?", (run_id,)).fetchone()
        return self._decode_run(dict(row))

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.memory.connection() as db:
            row = db.execute("SELECT * FROM assistant_runs WHERE id=?", (run_id,)).fetchone()
        return self._decode_run(dict(row)) if row else None

    def request_cancel(self, run_id: str) -> dict[str, Any] | None:
        with self.memory.connection() as db:
            row = db.execute("SELECT status FROM assistant_runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                return None
            if row["status"] == "running":
                db.execute(
                    "UPDATE assistant_runs SET status='cancel_requested' WHERE id=?",
                    (run_id,),
                )
        return self.get_run(run_id)

    def is_cancel_requested(self, run_id: str) -> bool:
        with self.memory.connection() as db:
            row = db.execute("SELECT status FROM assistant_runs WHERE id=?", (run_id,)).fetchone()
        return bool(row and row["status"] == "cancel_requested")

    def mark_cancelled(self, run_id: str) -> dict[str, Any] | None:
        now = self._now()
        with self.memory.connection() as db:
            db.execute(
                "UPDATE assistant_runs SET status='cancelled', error_code='cancelled_by_user', "
                "finished_at=? WHERE id=? AND status IN ('running','cancel_requested')",
                (now, run_id),
            )
        return self.get_run(run_id)

    @staticmethod
    def _decode_run(item: dict[str, Any]) -> dict[str, Any]:
        item["policy_decision"] = json.loads(item.pop("policy_decision_json") or "{}")
        item["budget"] = json.loads(item.pop("budget_json") or "{}")
        item["usage"] = json.loads(item.pop("usage_json") or "{}")
        return item

    def record_step(self, run_id: str, *, skill_name: str, inputs: dict[str, Any],
                    status: str, usage: dict[str, Any], observation: dict[str, Any]) -> None:
        now = self._now()
        fingerprint = hashlib.sha256(self._json(inputs).encode("utf-8")).hexdigest()
        with self.memory.connection() as db:
            step_index = int(db.execute(
                "SELECT COALESCE(MAX(step_index), -1) + 1 FROM assistant_steps WHERE run_id=?",
                (run_id,),
            ).fetchone()[0])
            db.execute(
                "INSERT INTO assistant_steps VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), run_id, step_index, skill_name, fingerprint, status, self._json(usage),
                 self._json(observation), now, now),
            )

    def create_proposal(self, run_id: str, *, proposal_type: str, target_ref: str,
                        target_version: str, payload: dict[str, Any], risk: str = "low") -> dict[str, Any]:
        proposal_id, now = str(uuid.uuid4()), self._now()
        payload_json = self._json(payload)
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        with self.memory.connection() as db:
            db.execute(
                "INSERT INTO assistant_proposals(id,run_id,proposal_type,target_ref,target_version,payload_json,"
                "payload_hash,risk,status,created_at,applied_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, NULL)",
                (proposal_id, run_id, proposal_type, target_ref, target_version, payload_json,
                 payload_hash, risk, now),
            )
        return {"id": proposal_id, "run_id": run_id, "proposal_type": proposal_type,
                "target_ref": target_ref, "target_version": target_version, "payload": payload,
                "payload_hash": payload_hash, "risk": risk, "status": "pending", "created_at": now}

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with self.memory.connection() as db:
            row = db.execute("SELECT * FROM assistant_proposals WHERE id=?", (proposal_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json"))
        return item

    def list_pending_proposals(self, session_id: str) -> list[dict[str, Any]]:
        with self.memory.connection() as db:
            rows = db.execute(
                "SELECT p.* FROM assistant_proposals p JOIN assistant_runs r ON r.id=p.run_id "
                "WHERE r.session_id=? AND p.status='pending' ORDER BY p.created_at",
                (session_id,),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            item.pop("confirmation_token_hash", None)
            item.pop("confirmation_expires_at", None)
            items.append(item)
        return items

    def list_actionable_proposals(self, session_id: str) -> list[dict[str, Any]]:
        with self.memory.connection() as db:
            rows = db.execute(
                "SELECT p.* FROM assistant_proposals p JOIN assistant_runs r ON r.id=p.run_id "
                "WHERE r.session_id=? AND p.status IN ('pending','applied') ORDER BY p.created_at",
                (session_id,),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            item.pop("confirmation_token_hash", None)
            item.pop("confirmation_expires_at", None)
            items.append(item)
        return items

    def undo_proposal(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            raise KeyError(proposal_id)
        if proposal["status"] != "applied":
            raise ValueError(f"Proposal is {proposal['status']}, not applied")
        if proposal["proposal_type"] != "resume_text_rewrite":
            raise ValueError("This proposal type must be restored from version history")
        with self.memory.connection() as db:
            db.execute("UPDATE assistant_proposals SET status='undone' WHERE id=?", (proposal_id,))
        return self.get_proposal(proposal_id) or proposal

    def set_proposal_status(self, proposal_id: str, status: str) -> dict[str, Any] | None:
        now = self._now()
        with self.memory.connection() as db:
            db.execute("UPDATE assistant_proposals SET status=?, applied_at=? WHERE id=?",
                       (status, now if status == "applied" else None, proposal_id))
        return self.get_proposal(proposal_id)

    def issue_confirmation_token(self, proposal_id: str, ttl_seconds: int = 600) -> str:
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            raise KeyError(proposal_id)
        if proposal["status"] != "pending":
            raise ValueError(f"Proposal is already {proposal['status']}")
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
        with self.memory.connection() as db:
            db.execute(
                "UPDATE assistant_proposals SET confirmation_token_hash=?, confirmation_expires_at=? WHERE id=?",
                (token_hash, expires_at, proposal_id),
            )
        return token

    def apply_proposal_with_token(self, proposal_id: str, token: str) -> dict[str, Any]:
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            raise KeyError(proposal_id)
        if proposal["status"] != "pending":
            raise ValueError(f"Proposal is already {proposal['status']}")
        expected = str(proposal.get("confirmation_token_hash") or "")
        actual = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires = proposal.get("confirmation_expires_at")
        if not expected or not secrets.compare_digest(expected, actual):
            raise ValueError("Invalid confirmation token")
        if not expires or datetime.fromisoformat(expires) <= datetime.now(timezone.utc):
            raise ValueError("Confirmation token expired")
        with self.memory.connection() as db:
            db.execute(
                "UPDATE assistant_proposals SET status='applied', applied_at=?, confirmation_token_hash=NULL, "
                "confirmation_expires_at=NULL WHERE id=? AND status='pending'",
                (self._now(), proposal_id),
            )
        return self.get_proposal(proposal_id) or proposal
