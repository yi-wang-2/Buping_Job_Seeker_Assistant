import json
from datetime import datetime, timezone

import pytest

from src.libs.ai_engine.knowledge import KnowledgeQuery, KnowledgeRegistry, KnowledgeSource
from src.libs.ai_engine.knowledge.adapters import GitSourceAdapter, JSONAdapter, MarkdownAdapter
from src.libs.ai_engine.knowledge.repository import SQLiteKnowledgeRepository


def _source(path, source_type="local_file"):
    return KnowledgeSource(
        id="source", name="测试知识", source_type=source_type, location=str(path),
        domain_pack="interview", created_at=datetime.now(timezone.utc), license="test-only",
    )


def _registry(tmp_path):
    registry = KnowledgeRegistry(SQLiteKnowledgeRepository(tmp_path / "knowledge.sqlite3"))
    registry.register_adapter("local_file", MarkdownAdapter())
    registry.register_adapter("markdown", MarkdownAdapter())
    registry.register_adapter("json", JSONAdapter())
    registry.register_adapter("git", GitSourceAdapter())
    return registry


def test_markdown_preview_splits_by_heading_and_syncs_to_fts(tmp_path):
    path = tmp_path / "concepts.md"
    path.write_text("# 数据库索引\nB+ 树索引适合范围查询。\n\n## 代价\n索引会增加写入成本。\n", encoding="utf-8")
    registry = _registry(tmp_path)
    source = _source(path, "markdown")

    preview = registry.preview(source)
    assert [unit.title for unit in preview.units] == ["数据库索引", "代价"]
    assert registry.sync(source)["created"] == 2
    result = registry.repository.search(KnowledgeQuery(text="索引"))
    assert result.hits
    assert result.hits[0].unit.title == "数据库索引"


def test_json_adapter_keeps_question_answer_intent_together(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"Java": [{
        "question": "HashMap 如何扩容？", "answer": "容量翻倍。",
        "thinking": "考察集合底层实现", "competencies": ["Java 集合"],
        "role": "Java 后端工程师",
    }]}, ensure_ascii=False), encoding="utf-8")
    registry = _registry(tmp_path)
    preview = registry.preview(_source(path, "json"))

    assert preview.unit_count == 1
    unit = preview.units[0]
    assert unit.unit_type == "question_card"
    assert unit.metadata["reference_answer"] == "容量翻倍。"
    assert unit.metadata["interviewer_intent"] == "考察集合底层实现"


def test_registry_deduplicates_questions_and_requires_warning_acceptance(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps([
        {"question": "什么是索引？", "answer": "数据结构", "thinking": "基础"},
        {"question": "什么是索引？", "answer": "B+ 树", "thinking": "基础"},
        {"question": "密钥检查", "answer": "api_key=abcdefghijklmnop", "thinking": "安全"},
    ], ensure_ascii=False), encoding="utf-8")
    registry = _registry(tmp_path)
    source = _source(path, "json")
    preview = registry.preview(source)
    assert preview.duplicate_count == 1
    assert preview.warnings
    with pytest.raises(ValueError, match="warnings"):
        registry.sync(source)
    assert registry.sync(source, accept_warnings=True)["created"] == 2


def test_git_adapter_reads_checked_out_tree_without_network(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Agent\nReAct 结合推理和行动。", encoding="utf-8")
    (repo / "ignored.txt").write_text("不支持", encoding="utf-8")
    registry = _registry(tmp_path)

    preview = registry.preview(_source(repo, "git"))
    assert preview.document_count == 1
    assert preview.units[0].title == "Agent"
