from src.libs.ai_engine.memory import SQLiteMemoryRepository
from src.libs.ai_engine.models import LLMResponse, TokenUsage
from src.libs.ai_engine.optimization import PromptCache


def test_prompt_cache_persists_and_restores_usage(tmp_path):
    path = tmp_path / "cache.sqlite3"
    SQLiteMemoryRepository(path)
    cache = PromptCache(path)
    response = LLMResponse("ok", "fake", "test", TokenUsage(2, 1, 3))

    cache.put("key", response)
    restored = PromptCache(path).get("key")

    assert restored.content == "ok"
    assert restored.usage.total_tokens == 3

