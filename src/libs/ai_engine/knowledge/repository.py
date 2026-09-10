from __future__ import annotations

import json
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from .models import KnowledgeQuery, KnowledgeSource, KnowledgeUnit, RetrievalHit, RetrievalResult


class SQLiteKnowledgeRepository:
    """Local knowledge metadata and lexical index with scope-aware reads."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def migrate(self) -> None:
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS knowledge_sources (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    location TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    owner_id TEXT,
                    license TEXT,
                    domain_pack TEXT,
                    content_hash TEXT NOT NULL,
                    sync_status TEXT NOT NULL,
                    last_synced_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_units (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    unit_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    topic TEXT,
                    subtopics_json TEXT NOT NULL,
                    roles_json TEXT NOT NULL,
                    companies_json TEXT NOT NULL,
                    difficulty TEXT,
                    question_type TEXT,
                    language TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    source_url TEXT,
                    source_updated_at TEXT,
                    content_hash TEXT NOT NULL,
                    quality_score REAL NOT NULL,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY(source_id) REFERENCES knowledge_sources(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_units_source ON knowledge_units(source_id);
                CREATE INDEX IF NOT EXISTS idx_knowledge_units_domain_type
                    ON knowledge_units(domain, unit_type);
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_units_fts USING fts5(
                    unit_id UNINDEXED, title, content, topic, tags,
                    tokenize='unicode61'
                );
            """)

    @staticmethod
    def _dump(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _dt(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    def upsert_source(self, source: KnowledgeSource) -> None:
        values = source.model_dump()
        with self.connection() as db:
            db.execute(
                """INSERT INTO knowledge_sources(
                       id,name,source_type,location,scope,owner_id,license,domain_pack,
                       content_hash,sync_status,last_synced_at,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                       name=excluded.name,source_type=excluded.source_type,location=excluded.location,
                       scope=excluded.scope,owner_id=excluded.owner_id,license=excluded.license,
                       domain_pack=excluded.domain_pack,content_hash=excluded.content_hash,
                       sync_status=excluded.sync_status,last_synced_at=excluded.last_synced_at""",
                (
                    values["id"], values["name"], values["source_type"], values["location"],
                    values["scope"], values["owner_id"], values["license"], values["domain_pack"],
                    values["content_hash"], values["sync_status"], self._dt(values["last_synced_at"]),
                    self._dt(values["created_at"]),
                ),
            )

    def get_source(self, source_id: str) -> KnowledgeSource | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM knowledge_sources WHERE id=?", (source_id,)).fetchone()
        return KnowledgeSource.model_validate(dict(row)) if row else None

    def list_sources(self, *, user_id: str = "local", session_id: str | None = None) -> list[KnowledgeSource]:
        clauses = ["scope='public'", "(scope='user' AND owner_id=?)"]
        params: list[object] = [user_id]
        if session_id:
            clauses.append("(scope='session' AND owner_id=?)")
            params.append(session_id)
        with self.connection() as db:
            rows = db.execute(
                f"SELECT * FROM knowledge_sources WHERE {' OR '.join(clauses)} ORDER BY created_at",
                params,
            ).fetchall()
        return [KnowledgeSource.model_validate(dict(row)) for row in rows]

    def sync_units(self, source_id: str, units: Iterable[KnowledgeUnit]) -> dict[str, int]:
        incoming = list(units)
        if any(unit.source_id != source_id for unit in incoming):
            raise ValueError("all units must belong to the synchronized source")
        incoming_ids = {unit.id for unit in incoming}
        created = updated = unchanged = deleted = 0
        with self.connection() as db:
            if not db.execute("SELECT 1 FROM knowledge_sources WHERE id=?", (source_id,)).fetchone():
                raise KeyError("knowledge source does not exist")
            existing = {
                row["id"]: row["content_hash"] for row in db.execute(
                    "SELECT id,content_hash FROM knowledge_units WHERE source_id=?", (source_id,),
                )
            }
            for unit in incoming:
                if existing.get(unit.id) == unit.content_hash:
                    unchanged += 1
                    continue
                row = unit.model_dump()
                existed = unit.id in existing
                if existed:
                    db.execute("DELETE FROM knowledge_units_fts WHERE unit_id=?", (unit.id,))
                db.execute(
                    """INSERT INTO knowledge_units(
                           id,source_id,unit_type,title,content,domain,topic,subtopics_json,
                           roles_json,companies_json,difficulty,question_type,language,source_path,
                           source_url,source_updated_at,content_hash,quality_score,metadata_json
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET
                           source_id=excluded.source_id,unit_type=excluded.unit_type,title=excluded.title,
                           content=excluded.content,domain=excluded.domain,topic=excluded.topic,
                           subtopics_json=excluded.subtopics_json,roles_json=excluded.roles_json,
                           companies_json=excluded.companies_json,difficulty=excluded.difficulty,
                           question_type=excluded.question_type,language=excluded.language,
                           source_path=excluded.source_path,source_url=excluded.source_url,
                           source_updated_at=excluded.source_updated_at,content_hash=excluded.content_hash,
                           quality_score=excluded.quality_score,metadata_json=excluded.metadata_json""",
                    (
                        row["id"], row["source_id"], row["unit_type"], row["title"], row["content"],
                        row["domain"], row["topic"], self._dump(row["subtopics"]), self._dump(row["roles"]),
                        self._dump(row["companies"]), row["difficulty"], row["question_type"], row["language"],
                        row["source_path"], row["source_url"], self._dt(row["source_updated_at"]),
                        row["content_hash"], row["quality_score"], self._dump(row["metadata"]),
                    ),
                )
                tags = " ".join((*row["subtopics"], *row["roles"], *row["companies"]))
                db.execute(
                    "INSERT INTO knowledge_units_fts(unit_id,title,content,topic,tags) VALUES(?,?,?,?,?)",
                    (unit.id, unit.title, unit.content, unit.topic or "", tags),
                )
                updated += int(existed)
                created += int(not existed)
            removed = sorted(set(existing) - incoming_ids)
            for unit_id in removed:
                db.execute("DELETE FROM knowledge_units_fts WHERE unit_id=?", (unit_id,))
                db.execute("DELETE FROM knowledge_units WHERE id=?", (unit_id,))
            deleted = len(removed)
            db.execute(
                "UPDATE knowledge_sources SET sync_status='ready',last_synced_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), source_id),
            )
        return {"created": created, "updated": updated, "unchanged": unchanged, "deleted": deleted}

    def delete_source(self, source_id: str) -> bool:
        with self.connection() as db:
            ids = [row[0] for row in db.execute("SELECT id FROM knowledge_units WHERE source_id=?", (source_id,))]
            for unit_id in ids:
                db.execute("DELETE FROM knowledge_units_fts WHERE unit_id=?", (unit_id,))
            result = db.execute("DELETE FROM knowledge_sources WHERE id=?", (source_id,))
        return result.rowcount > 0

    def set_source_status(self, source_id: str, status: str) -> KnowledgeSource:
        if status not in {"ready", "disabled"}:
            raise ValueError("source status must be ready or disabled")
        with self.connection() as db:
            result = db.execute(
                "UPDATE knowledge_sources SET sync_status=? WHERE id=?", (status, source_id),
            )
        if not result.rowcount:
            raise KeyError("knowledge source does not exist")
        source = self.get_source(source_id)
        if source is None:
            raise KeyError("knowledge source does not exist")
        return source

    def source_stats(self, source_id: str) -> dict[str, int | float]:
        with self.connection() as db:
            row = db.execute(
                """SELECT COUNT(*) AS units,
                          COALESCE(SUM(LENGTH(content)),0) AS characters,
                          COALESCE(AVG(quality_score),0) AS average_quality
                     FROM knowledge_units WHERE source_id=?""",
                (source_id,),
            ).fetchone()
        return {
            "units": int(row["units"]), "characters": int(row["characters"]),
            "average_quality": round(float(row["average_quality"]), 4),
        }

    @staticmethod
    def _decode_unit(row: sqlite3.Row) -> KnowledgeUnit:
        item = dict(row)
        for transient in ("rank", "vector", "dimension"):
            item.pop(transient, None)
        for field in ("subtopics", "roles", "companies", "metadata"):
            item[field] = json.loads(item.pop(f"{field}_json"))
        return KnowledgeUnit.model_validate(item)

    @staticmethod
    def _scope_sql(query: KnowledgeQuery) -> tuple[str, list[object]]:
        clauses: list[str] = []
        params: list[object] = []
        for scope in query.scopes:
            if scope == "public":
                clauses.append("s.scope='public'")
            elif scope == "user":
                clauses.append("(s.scope='user' AND s.owner_id=?)")
                params.append(query.user_id)
            elif scope == "session" and query.session_id:
                clauses.append("(s.scope='session' AND s.owner_id=?)")
                params.append(query.session_id)
            elif scope == "organization":
                clauses.append("(s.scope='organization' AND s.owner_id=?)")
                params.append(query.user_id)
        return "(" + " OR ".join(clauses or ["0"]) + ")", params

    @staticmethod
    def _lexical_terms(query: KnowledgeQuery) -> list[str]:
        text = " ".join([query.text, *query.topics, *query.roles, *query.companies]).casefold()
        terms = re.findall(r"[a-z][a-z0-9.+_-]*(?:\s+[a-z][a-z0-9.+_-]+)?", text)
        stop = {"如何", "什么", "怎样", "哪些", "应该", "一个", "进行", "问题", "面试", "中如", "何做"}
        for segment in re.findall(r"[\u4e00-\u9fff]{2,}", text):
            if len(segment) <= 8 and segment not in stop:
                terms.append(segment)
            for size in (2, 3, 4):
                terms.extend(
                    value for index in range(len(segment) - size + 1)
                    if (value := segment[index:index + size]) not in stop
                )
        return list(dict.fromkeys(term.strip() for term in terms if term.strip()))[:80]

    def _search_cjk(self, query: KnowledgeQuery, where: list[str], params: list[object],
                    started: float) -> RetrievalResult:
        terms = self._lexical_terms(query)
        with self.connection() as db:
            rows = db.execute(
                f"""SELECT u.* FROM knowledge_units u
                      JOIN knowledge_sources s ON s.id=u.source_id
                      WHERE {' AND '.join(where)} LIMIT 5000""",
                params,
            ).fetchall()
        weighted_total = sum(max(1, len(term)) for term in terms) or 1
        hits: list[RetrievalHit] = []
        for row in rows:
            unit = self._decode_unit(row)
            title = unit.title.casefold()
            haystack = f"{title}\n{unit.topic or ''}\n{unit.content}".casefold()
            matched = [term for term in terms if term in haystack]
            if not matched:
                continue
            coverage = sum(max(1, len(term)) for term in matched) / weighted_total
            title_coverage = sum(max(1, len(term)) for term in matched if term in title) / weighted_total
            phrase_bonus = .18 if query.text.casefold() in haystack else 0
            lexical = min(1.0, coverage * .82 + title_coverage * .35 + phrase_bonus)
            score = min(1.0, lexical * .85 + unit.quality_score * .15)
            hits.append(RetrievalHit(
                unit=unit, score=score, lexical_score=lexical,
                matched_terms=matched[:20], reasons=["CJK-aware lexical overlap"],
            ))
        hits.sort(key=lambda hit: (hit.lexical_score, hit.unit.quality_score), reverse=True)
        selected = hits[:query.top_k]
        return RetrievalResult(
            query=query, hits=selected, total_candidates=len(hits),
            truncated=len(hits) > len(selected),
            retrieval_ms=round((time.perf_counter() - started) * 1000, 3),
            index_version="lexical-cjk-v2", as_of=datetime.now(timezone.utc),
        )

    def search(self, query: KnowledgeQuery) -> RetrievalResult:
        started = time.perf_counter()
        scope_sql, params = self._scope_sql(query)
        where = [scope_sql, "s.sync_status='ready'"]
        if query.domain:
            where.append("u.domain=?")
            params.append(query.domain)
        if query.unit_types:
            where.append(f"u.unit_type IN ({','.join('?' for _ in query.unit_types)})")
            params.extend(query.unit_types)
        if query.difficulty:
            where.append("u.difficulty=?")
            params.append(query.difficulty)
        if query.question_type:
            where.append("u.question_type=?")
            params.append(query.question_type)
        for column, values in (
            ("roles_json", query.roles), ("companies_json", query.companies),
            ("topic", query.topics),
        ):
            if values:
                where.append("(" + " OR ".join(f"u.{column} LIKE ? ESCAPE '\\'" for _ in values) + ")")
                params.extend(
                    "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                    for value in values
                )
        if query.exclude_unit_ids:
            where.append(f"u.id NOT IN ({','.join('?' for _ in query.exclude_unit_ids)})")
            params.extend(query.exclude_unit_ids)
        if query.source_ids:
            where.append(f"u.source_id IN ({','.join('?' for _ in query.source_ids)})")
            params.extend(query.source_ids)
        if re.search(r"[\u4e00-\u9fff]", query.text):
            return self._search_cjk(query, where, params, started)
        # FTS syntax is kept out of user control: quoted terms are joined with OR.
        terms = list(dict.fromkeys([
            *query.topics, *query.roles, *query.companies,
            *(term for term in query.text.replace('"', " ").split() if term),
        ]))[:20]
        fts_query = " OR ".join(f'"{term}"' for term in terms) or '"__no_match__"'
        # unicode61 does not split every CJK word boundary. Use bound LIKE parameters
        # when a short CJK term is present, while keeping FTS/BM25 for normal terms.
        use_like = any(len(term) < 3 and re.search(r"[\u4e00-\u9fff]", term) for term in terms)
        if use_like:
            escaped = [term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") for term in terms]
            match_sql = "(" + " OR ".join(
                "u.title LIKE ? ESCAPE '\\' OR u.content LIKE ? ESCAPE '\\' OR COALESCE(u.topic,'') LIKE ? ESCAPE '\\'"
                for _ in escaped
            ) + ")"
            match_params = [value for term in escaped for value in (f"%{term}%",) * 3]
            from_sql = "knowledge_units u JOIN knowledge_sources s ON s.id=u.source_id"
            select_sql = "u.*, 0.0 AS rank"
        else:
            match_sql = "knowledge_units_fts MATCH ?"
            match_params = [fts_query]
            from_sql = (
                "knowledge_units_fts JOIN knowledge_units u ON u.id=knowledge_units_fts.unit_id "
                "JOIN knowledge_sources s ON s.id=u.source_id"
            )
            select_sql = "u.*, bm25(knowledge_units_fts) AS rank"
        sql = f"""SELECT {select_sql} FROM {from_sql}
                  WHERE {match_sql} AND {' AND '.join(where)}
                  ORDER BY rank ASC, u.quality_score DESC LIMIT ?"""
        with self.connection() as db:
            total_candidates = int(db.execute(
                f"SELECT COUNT(*) FROM {from_sql} WHERE {match_sql} AND {' AND '.join(where)}",
                [*match_params, *params],
            ).fetchone()[0])
            rows = db.execute(sql, [*match_params, *params, query.top_k]).fetchall()
        hits = []
        for row in rows:
            rank = abs(float(row["rank"] or 0))
            lexical = 1 / (1 + rank)
            unit = self._decode_unit(row)
            hits.append(RetrievalHit(
                unit=unit, score=min(1.0, lexical * .8 + unit.quality_score * .2),
                lexical_score=min(1.0, lexical), matched_terms=terms,
                reasons=["FTS5/BM25 keyword match"],
            ))
        return RetrievalResult(
            query=query,
            hits=hits,
            total_candidates=total_candidates,
            truncated=total_candidates > len(hits),
            retrieval_ms=round((time.perf_counter() - started) * 1000, 3),
            index_version="fts5-v1",
            as_of=datetime.now(timezone.utc),
        )
