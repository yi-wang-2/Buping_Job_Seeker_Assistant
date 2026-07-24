from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class MemoryItem:
    namespace: str
    key: str
    value: Any
    user_id: str = "local"
    source: str = "user"
    confidence: float = 1.0
    importance: int = 50
    status: str = "active"
    id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None

