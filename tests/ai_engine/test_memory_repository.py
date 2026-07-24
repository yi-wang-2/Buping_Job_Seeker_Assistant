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

