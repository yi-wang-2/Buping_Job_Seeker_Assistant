from datetime import datetime, timezone

from src.libs.ai_engine.knowledge import KnowledgeQuery, KnowledgeSource, KnowledgeUnit
from src.libs.ai_engine.knowledge.repository import SQLiteKnowledgeRepository


def _source(source_id="public", scope="public", owner_id=None):
    return KnowledgeSource(
        id=source_id, name=source_id, source_type="json", location=f"{source_id}.json",
        scope=scope, owner_id=owner_id, created_at=datetime.now(timezone.utc),
    )


def _unit(unit_id, source_id="public", content="HashMap 扩容与并发边界", content_hash="h1"):
    return KnowledgeUnit(
        id=unit_id, source_id=source_id, unit_type="question_card", title="HashMap 扩容",
        content=content, domain="interview", topic="Java", roles=["Java 后端工程师"],
        source_path=f"data.json#{unit_id}", content_hash=content_hash, quality_score=.8,
        metadata={
            "question": "HashMap 如何扩容？", "reference_answer": "容量翻倍",
            "competencies": ["Java 集合"], "interviewer_intent": "考察实现细节",
        },
    )


def test_incremental_sync_tracks_create_update_unchanged_and_delete(tmp_path):
    repo = SQLiteKnowledgeRepository(tmp_path / "knowledge.sqlite3")
    repo.upsert_source(_source())

    assert repo.sync_units("public", [_unit("u1"), _unit("u2")]) == {
        "created": 2, "updated": 0, "unchanged": 0, "deleted": 0,
    }
    assert repo.sync_units("public", [_unit("u1"), _unit("u2", content="更新内容", content_hash="h2")]) == {
        "created": 0, "updated": 1, "unchanged": 1, "deleted": 0,
    }
    assert repo.sync_units("public", [_unit("u2", content="更新内容", content_hash="h2")]) == {
        "created": 0, "updated": 0, "unchanged": 1, "deleted": 1,
    }


def test_fts_search_respects_scope_and_metadata_filters(tmp_path):
    repo = SQLiteKnowledgeRepository(tmp_path / "knowledge.sqlite3")
    repo.upsert_source(_source())
    repo.sync_units("public", [_unit("public-unit")])
    repo.upsert_source(_source("private", "user", "alice"))
    repo.sync_units("private", [_unit("private-unit", "private", "HashMap 私有面经", "private-hash")])

    public = repo.search(KnowledgeQuery(text="HashMap", topics=["Java"], scopes=["public"]))
    assert [hit.unit.id for hit in public.hits] == ["public-unit"]
    alice = repo.search(KnowledgeQuery(text="HashMap", scopes=["public", "user"], user_id="alice"))
    assert {hit.unit.id for hit in alice.hits} == {"public-unit", "private-unit"}
    bob = repo.search(KnowledgeQuery(text="HashMap", scopes=["public", "user"], user_id="bob"))
    assert [hit.unit.id for hit in bob.hits] == ["public-unit"]


def test_source_delete_removes_units_and_fts_entries(tmp_path):
    repo = SQLiteKnowledgeRepository(tmp_path / "knowledge.sqlite3")
    repo.upsert_source(_source())
    repo.sync_units("public", [_unit("u1")])
    assert repo.delete_source("public") is True
    assert repo.search(KnowledgeQuery(text="HashMap")).hits == []


def test_source_id_filter_limits_otherwise_visible_sources(tmp_path):
    repo = SQLiteKnowledgeRepository(tmp_path / "knowledge.sqlite3")
    repo.upsert_source(_source("one"))
    repo.upsert_source(_source("two"))
    repo.sync_units("one", [_unit("one-unit", "one")])
    repo.sync_units("two", [_unit("two-unit", "two")])

    result = repo.search(KnowledgeQuery(text="HashMap", source_ids=["two"]))

    assert [hit.unit.id for hit in result.hits] == ["two-unit"]
