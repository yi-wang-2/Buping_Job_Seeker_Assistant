from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import time

from .models import KnowledgeQuery, RetrievalHit, RetrievalResult
from .repository import SQLiteKnowledgeRepository
from .vector import SQLiteVectorIndex


class HybridKnowledgeRetriever:
    def __init__(self, repository: SQLiteKnowledgeRepository, vector_index: SQLiteVectorIndex | None = None) -> None:
        self.repository = repository
        self.vector_index = vector_index

    @staticmethod
    def _metadata_boost(hit: RetrievalHit, query: KnowledgeQuery) -> float:
        boost = 0.0
        if query.roles and set(query.roles) & set(hit.unit.roles):
            boost += .08
        if query.companies and set(query.companies) & set(hit.unit.companies):
            boost += .08
        if query.topics and hit.unit.topic and any(topic.casefold() in hit.unit.topic.casefold() for topic in query.topics):
            boost += .08
        return boost

    def retrieve(self, query: KnowledgeQuery) -> RetrievalResult:
        started = time.perf_counter()
        candidate_query = query.model_copy(update={"top_k": min(50, query.top_k * 3)})
        lexical = self.repository.search(candidate_query)
        semantic = self.vector_index.search(candidate_query, limit=candidate_query.top_k) if self.vector_index else []
        merged: dict[str, RetrievalHit] = {}
        ranks: dict[str, float] = {}
        for channel_weight, hits in ((.55, lexical.hits), (.45, semantic)):
            for rank, hit in enumerate(hits, start=1):
                unit_id = hit.unit.id
                ranks[unit_id] = ranks.get(unit_id, 0) + channel_weight / (60 + rank)
                current = merged.get(unit_id)
                if current is None:
                    merged[unit_id] = hit
                else:
                    merged[unit_id] = current.model_copy(update={
                        "lexical_score": max(current.lexical_score, hit.lexical_score),
                        "semantic_score": max(current.semantic_score, hit.semantic_score),
                        "reasons": list(dict.fromkeys([*current.reasons, *hit.reasons])),
                    })
        maximum_rrf = .55 / 61 + (.45 / 61 if self.vector_index else 0)
        reranked = []
        for unit_id, hit in merged.items():
            rrf = ranks[unit_id] / maximum_rrf if maximum_rrf else 0
            final = min(1.0, .72 * rrf + .18 * hit.unit.quality_score + self._metadata_boost(hit, query))
            reranked.append(hit.model_copy(update={
                "score": final, "rerank_score": final,
                "reasons": [*hit.reasons, "RRF merge and metadata/quality rerank"],
            }))
        reranked.sort(key=lambda hit: (hit.score, hit.unit.quality_score), reverse=True)
        hits = reranked[:query.top_k]
        warnings = [] if self.vector_index else ["semantic retrieval unavailable; used lexical retrieval only"]
        return RetrievalResult(
            query=query, hits=hits, total_candidates=len(merged), truncated=len(merged) > len(hits),
            retrieval_ms=round((time.perf_counter() - started) * 1000, 3),
            index_version="hybrid-v1" if self.vector_index else "fts5-v1",
            as_of=datetime.now(timezone.utc), warnings=warnings,
        )
