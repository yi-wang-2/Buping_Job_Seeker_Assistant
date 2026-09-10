from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import KnowledgeSource, KnowledgeUnit, RawKnowledgeUnit
from .protocols import KnowledgeSourceAdapter
from .repository import SQLiteKnowledgeRepository
from .domain_packs import DomainPackRegistry


class ImportPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    document_count: int
    unit_count: int
    duplicate_count: int
    rejected_count: int
    warnings: list[str] = Field(default_factory=list)
    units: list[KnowledgeUnit] = Field(default_factory=list)


class KnowledgeRegistry:
    def __init__(self, repository: SQLiteKnowledgeRepository, domain_packs: DomainPackRegistry | None = None) -> None:
        self.repository = repository
        self.adapters: dict[str, KnowledgeSourceAdapter] = {}
        self.domain_packs = domain_packs or DomainPackRegistry()

    def register_adapter(self, source_type: str, adapter: KnowledgeSourceAdapter) -> None:
        if source_type in self.adapters:
            raise ValueError(f"adapter already registered: {source_type}")
        self.adapters[source_type] = adapter

    def _unit(self, source: KnowledgeSource, raw: RawKnowledgeUnit) -> KnowledgeUnit:
        unit_id = hashlib.sha256(
            f"{source.id}|{raw.source_path}|{raw.unit_type}".encode()
        ).hexdigest()[:32]
        metadata = self.domain_packs.get(source.domain_pack).enrich(
            raw.title, raw.content, raw.metadata,
        )
        content_hash = hashlib.sha256(json.dumps({
            "normalizer_version": 2, "content": raw.content, "metadata": metadata,
        }, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        topic = str(metadata.get("topic") or metadata.get("category") or "").strip() or None
        roles = [str(metadata["role"])] if metadata.get("role") else []
        companies = [str(metadata["company"])] if metadata.get("company") else []
        difficulty = str(metadata.get("difficulty") or "").lower() or None
        if difficulty not in {"introductory", "intermediate", "advanced", "expert"}:
            difficulty = None
        return KnowledgeUnit(
            id=unit_id, source_id=source.id, unit_type=raw.unit_type, title=raw.title,
            content=raw.content, domain=source.domain_pack or "interview", topic=topic,
            subtopics=list(metadata.get("subtopics") or []), roles=roles, companies=companies,
            difficulty=difficulty, question_type=metadata.get("question_type"), source_path=raw.source_path,
            source_url=source.location if source.source_type in {"git", "web"} else None,
            content_hash=content_hash, quality_score=.8 if raw.unit_type == "question_card" else .6,
            metadata=metadata,
        )

    def preview(self, source: KnowledgeSource) -> ImportPreview:
        adapter = self.adapters.get(source.source_type)
        if not adapter:
            raise LookupError(f"no adapter for source type: {source.source_type}")
        documents = adapter.discover(source)
        units: list[KnowledgeUnit] = []
        rejected = 0
        warnings: list[str] = []
        seen: set[tuple[str, str]] = set()
        duplicate_count = 0
        for document in documents:
            if re.search(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{12,}", document.content):
                warnings.append(f"potential secret detected: {document.metadata.get('relative_path', document.path)}")
            for raw in adapter.parse(document):
                if not raw.content.strip() or raw.content.strip() in {"```", "```bash", "```json", "```python"}:
                    rejected += 1
                    continue
                try:
                    unit = self._unit(source, raw)
                except ValueError:
                    rejected += 1
                    continue
                duplicate_key = (unit.unit_type, re.sub(r"\W+", "", unit.title.casefold()))
                if duplicate_key in seen:
                    duplicate_count += 1
                    continue
                seen.add(duplicate_key)
                units.append(unit)
        return ImportPreview(
            source_id=source.id, document_count=len(documents), unit_count=len(units),
            duplicate_count=duplicate_count, rejected_count=rejected,
            warnings=list(dict.fromkeys(warnings)), units=units,
        )

    def sync(self, source: KnowledgeSource, *, accept_warnings: bool = False) -> dict[str, Any]:
        preview = self.preview(source)
        if preview.warnings and not accept_warnings:
            raise ValueError("knowledge import has warnings; preview and explicitly accept them")
        now = datetime.now(timezone.utc)
        source_hash = hashlib.sha256(
            "|".join(sorted(unit.content_hash for unit in preview.units)).encode()
        ).hexdigest()
        ready_source = source.model_copy(update={
            "content_hash": source_hash, "sync_status": "syncing", "last_synced_at": now,
        })
        self.repository.upsert_source(ready_source)
        stats = self.repository.sync_units(source.id, preview.units)
        return {**stats, "source_id": source.id, "preview": preview.model_dump(exclude={"units"})}
