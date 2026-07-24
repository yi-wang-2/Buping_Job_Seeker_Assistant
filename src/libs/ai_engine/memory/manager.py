from __future__ import annotations

from .models import MemoryItem
from .repository import SQLiteMemoryRepository


class MemoryManager:
    def __init__(self, repository: SQLiteMemoryRepository) -> None:
        self.repository = repository

    @property
    def enabled(self) -> bool:
        return bool(self.repository.get_setting("memory_enabled", True))

    def remember(self, item: MemoryItem) -> MemoryItem | None:
        if not self.enabled:
            return None
        if item.source != "user" and item.confidence < 0.8:
            return None
        return self.repository.upsert_memory(item)

    def recall(self, user_id: str = "local", namespace: str = "") -> list[MemoryItem]:
        return self.repository.list_memories(user_id, namespace) if self.enabled else []

