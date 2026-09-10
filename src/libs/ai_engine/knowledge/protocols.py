from __future__ import annotations

from typing import Protocol

from .models import KnowledgeSource, RawKnowledgeUnit, SourceDocument


class KnowledgeSourceAdapter(Protocol):
    """K1 boundary: adapters discover and parse; repositories normalize and index."""

    def discover(self, source: KnowledgeSource) -> list[SourceDocument]: ...

    def parse(self, document: SourceDocument) -> list[RawKnowledgeUnit]: ...

    def fingerprint(self, document: SourceDocument) -> str: ...
