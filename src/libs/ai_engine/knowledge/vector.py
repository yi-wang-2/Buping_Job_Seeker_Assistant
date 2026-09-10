from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Protocol, Sequence

import numpy as np

from .models import KnowledgeQuery, KnowledgeUnit, RetrievalHit
from .repository import SQLiteKnowledgeRepository


class EmbeddingProvider(Protocol):
    model_id: str
    dimension: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class HashingEmbeddingProvider:
    """Dependency-free deterministic fallback used for local/offline retrieval."""

    model_id = "hashing-char-ngram-v1"

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            normalized = re.sub(r"\s+", " ", text.casefold()).strip()
            tokens = [normalized[index:index + 3] for index in range(max(1, len(normalized) - 2))]
            vector = np.zeros(self.dimension, dtype=np.float32)
            for token in tokens:
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimension
                vector[index] += -1.0 if digest[4] & 1 else 1.0
            norm = float(np.linalg.norm(vector))
            if norm:
                vector /= norm
            vectors.append(vector.tolist())
        return vectors


class SentenceTransformerEmbeddingProvider:
    """Lazy adapter; callers provide a local model name/path and control download policy."""

    def __init__(self, model_name_or_path: str, *, local_files_only: bool = True) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name_or_path, local_files_only=local_files_only)
        self.model_id = f"sentence-transformers:{model_name_or_path}"
        self.dimension = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        values = self._model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(values, dtype=np.float32).tolist()


class SQLiteVectorIndex:
    def __init__(self, repository: SQLiteKnowledgeRepository, provider: EmbeddingProvider) -> None:
        self.repository = repository
        self.provider = provider
        with self.repository.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                unit_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                vector BLOB NOT NULL,
                PRIMARY KEY(unit_id, model_id),
                FOREIGN KEY(unit_id) REFERENCES knowledge_units(id) ON DELETE CASCADE
            )""")

    @staticmethod
    def _text(unit: KnowledgeUnit) -> str:
        return "\n".join(filter(None, [unit.title, unit.topic or "", " ".join(unit.subtopics), unit.content]))

    def index_units(self, units: Sequence[KnowledgeUnit]) -> dict[str, int]:
        if not units:
            return {"indexed": 0, "unchanged": 0}
        with self.repository.connection() as db:
            existing = {
                row["unit_id"]: row["content_hash"] for row in db.execute(
                    "SELECT unit_id,content_hash FROM knowledge_embeddings WHERE model_id=?",
                    (self.provider.model_id,),
                )
            }
        changed = [unit for unit in units if existing.get(unit.id) != unit.content_hash]
        vectors = self.provider.embed([self._text(unit) for unit in changed])
        with self.repository.connection() as db:
            for unit, vector in zip(changed, vectors, strict=True):
                array = np.asarray(vector, dtype=np.float32)
                if array.size != self.provider.dimension or not np.isfinite(array).all():
                    raise ValueError("embedding provider returned an invalid vector")
                norm = float(np.linalg.norm(array))
                if norm:
                    array /= norm
                db.execute(
                    """INSERT INTO knowledge_embeddings(unit_id,model_id,dimension,content_hash,vector)
                       VALUES(?,?,?,?,?) ON CONFLICT(unit_id,model_id) DO UPDATE SET
                       dimension=excluded.dimension,content_hash=excluded.content_hash,vector=excluded.vector""",
                    (unit.id, self.provider.model_id, self.provider.dimension, unit.content_hash, array.tobytes()),
                )
        return {"indexed": len(changed), "unchanged": len(units) - len(changed)}

    def search(self, query: KnowledgeQuery, *, limit: int | None = None) -> list[RetrievalHit]:
        query_vector = np.asarray(self.provider.embed([query.text])[0], dtype=np.float32)
        norm = float(np.linalg.norm(query_vector))
        if norm:
            query_vector /= norm
        scope_sql, params = self.repository._scope_sql(query)
        where = [scope_sql, "s.sync_status='ready'", "e.model_id=?"]
        params.append(self.provider.model_id)
        if query.domain:
            where.append("u.domain=?")
            params.append(query.domain)
        if query.unit_types:
            where.append(f"u.unit_type IN ({','.join('?' for _ in query.unit_types)})")
            params.extend(query.unit_types)
        if query.exclude_unit_ids:
            where.append(f"u.id NOT IN ({','.join('?' for _ in query.exclude_unit_ids)})")
            params.extend(query.exclude_unit_ids)
        if query.source_ids:
            where.append(f"u.source_id IN ({','.join('?' for _ in query.source_ids)})")
            params.extend(query.source_ids)
        with self.repository.connection() as db:
            rows = db.execute(
                f"""SELECT u.*,e.vector,e.dimension FROM knowledge_embeddings e
                      JOIN knowledge_units u ON u.id=e.unit_id
                      JOIN knowledge_sources s ON s.id=u.source_id
                      WHERE {' AND '.join(where)}""",
                params,
            ).fetchall()
        scored = []
        for row in rows:
            vector = np.frombuffer(row["vector"], dtype=np.float32)
            if vector.size != query_vector.size:
                continue
            cosine = float(np.dot(query_vector, vector))
            semantic = max(0.0, min(1.0, (cosine + 1) / 2))
            unit = self.repository._decode_unit(row)
            scored.append(RetrievalHit(
                unit=unit, score=semantic, semantic_score=semantic,
                reasons=[f"semantic similarity via {self.provider.model_id}"],
            ))
        scored.sort(key=lambda hit: (hit.semantic_score, hit.unit.quality_score), reverse=True)
        return scored[: limit or query.top_k]
