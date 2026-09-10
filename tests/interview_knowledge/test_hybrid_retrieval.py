from datetime import datetime, timezone

from src.libs.ai_engine.knowledge import (
    HashingEmbeddingProvider,
    HybridKnowledgeRetriever,
    KnowledgeQuery,
    KnowledgeSource,
    KnowledgeUnit,
    SQLiteKnowledgeRepository,
    SQLiteVectorIndex,
)


def _unit(unit_id, title, content, topic):
    return KnowledgeUnit(
        id=unit_id, source_id="public", unit_type="concept", title=title, content=content,
        domain="interview", topic=topic, source_path=f"knowledge.md#{unit_id}",
        content_hash=f"hash-{unit_id}", quality_score=.8,
    )


def _repository(tmp_path):
    repository = SQLiteKnowledgeRepository(tmp_path / "knowledge.sqlite3")
    repository.upsert_source(KnowledgeSource(
        id="public", name="公共知识", source_type="markdown", location="knowledge.md",
        created_at=datetime.now(timezone.utc), sync_status="pending",
    ))
    units = [
        _unit("rag", "RAG 检索", "RAG 使用检索、重排和引用降低幻觉。", "RAG"),
        _unit("react", "ReAct Agent", "ReAct 循环结合推理、工具行动和观察。", "Agent"),
        _unit("database", "数据库索引", "B+ 树索引适合范围查询。", "数据库"),
    ]
    repository.sync_units("public", units)
    return repository, units


def test_vector_index_is_incremental_and_scope_aware(tmp_path):
    repository, units = _repository(tmp_path)
    index = SQLiteVectorIndex(repository, HashingEmbeddingProvider(128))
    assert index.index_units(units) == {"indexed": 3, "unchanged": 0}
    assert index.index_units(units) == {"indexed": 0, "unchanged": 3}

    hits = index.search(KnowledgeQuery(text="RAG 检索和引用", top_k=2))
    assert hits[0].unit.id == "rag"
    assert hits[0].semantic_score > 0


def test_hybrid_retrieval_merges_channels_without_duplicates(tmp_path):
    repository, units = _repository(tmp_path)
    vector = SQLiteVectorIndex(repository, HashingEmbeddingProvider(128))
    vector.index_units(units)

    result = HybridKnowledgeRetriever(repository, vector).retrieve(
        KnowledgeQuery(text="RAG 检索", topics=["RAG"], top_k=2),
    )

    assert result.index_version == "hybrid-v1"
    assert result.hits[0].unit.id == "rag"
    assert len({hit.unit.id for hit in result.hits}) == len(result.hits)
    assert any("RRF" in reason for reason in result.hits[0].reasons)


def test_hybrid_retrieval_degrades_explicitly_without_vector_index(tmp_path):
    repository, _ = _repository(tmp_path)
    result = HybridKnowledgeRetriever(repository).retrieve(KnowledgeQuery(text="索引"))

    assert result.hits[0].unit.id == "database"
    assert result.index_version == "fts5-v1"
    assert result.warnings == ["semantic retrieval unavailable; used lexical retrieval only"]
