from src.libs.ai_engine.memory import MemoryItem, MemoryManager, SQLiteMemoryRepository


def test_memory_round_trip_and_clear(tmp_path):
    repo = SQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    saved = repo.upsert_memory(MemoryItem(namespace="job_preferences", key="city", value="上海"))

    assert repo.get_memory(saved.id).value == "上海"
    assert repo.list_memories(namespace="job_preferences")[0].key == "city"
    assert repo.clear_memories(namespace="job_preferences") == 1
    assert repo.list_memories() == []


def test_memory_manager_respects_privacy_switch(tmp_path):
    repo = SQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    repo.set_setting("memory_enabled", False)
    manager = MemoryManager(repo)

    assert manager.remember(MemoryItem(namespace="job_preferences", key="city", value="上海")) is None
    assert manager.recall() == []


def test_model_inferred_memory_requires_user_confirmation(tmp_path):
    repo = SQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    manager = MemoryManager(repo)

    candidate = manager.remember(MemoryItem(
        namespace="career_goals", key="inferred_role", value="AI Agent 开发",
        source="model", confidence=0.9,
    ))

    assert candidate is not None and candidate.status == "pending"
    assert manager.recall(namespace="career_goals") == []
    pending = repo.list_memory_candidates()
    assert pending[0]["value"] == "AI Agent 开发"

    saved = repo.review_memory_candidate(pending[0]["id"], accepted=True)

    assert saved is not None and saved.source == "user_confirmed"
    assert manager.recall(namespace="career_goals")[0].value == "AI Agent 开发"
    assert repo.list_memory_candidates() == []

