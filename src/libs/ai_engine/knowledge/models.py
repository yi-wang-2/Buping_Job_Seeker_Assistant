from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


KnowledgeScope = Literal["public", "organization", "user", "session"]
KnowledgeUnitType = Literal[
    "question_card", "concept", "interview_experience", "practical_case",
    "role_requirement", "user_evidence",
]


class KnowledgeSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=300)
    source_type: Literal[
        "git", "local_file", "markdown", "json", "pdf", "docx", "archive", "upload", "web",
    ]
    location: str = Field(min_length=1, max_length=2000)
    scope: KnowledgeScope = "public"
    owner_id: str | None = Field(default=None, max_length=200)
    license: str | None = Field(default=None, max_length=200)
    domain_pack: str | None = Field(default=None, max_length=200)
    content_hash: str = Field(default="", max_length=128)
    sync_status: Literal["pending", "previewed", "syncing", "ready", "failed", "disabled"] = "pending"
    last_synced_at: datetime | None = None
    created_at: datetime

    @model_validator(mode="after")
    def require_owner_for_private_scope(self) -> "KnowledgeSource":
        if self.scope in {"organization", "user", "session"} and not self.owner_id:
            raise ValueError(f"owner_id is required for {self.scope} knowledge")
        return self


class KnowledgeUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=200)
    unit_type: KnowledgeUnitType
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=100_000)
    domain: str = Field(min_length=1, max_length=100)
    topic: str | None = Field(default=None, max_length=200)
    subtopics: list[str] = Field(default_factory=list, max_length=30)
    roles: list[str] = Field(default_factory=list, max_length=30)
    companies: list[str] = Field(default_factory=list, max_length=30)
    difficulty: Literal["introductory", "intermediate", "advanced", "expert"] | None = None
    question_type: str | None = Field(default=None, max_length=100)
    language: Literal["zh", "en", "mixed"] = "zh"
    source_path: str = Field(min_length=1, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2000)
    source_updated_at: datetime | None = None
    content_hash: str = Field(min_length=1, max_length=128)
    quality_score: float = Field(default=0.5, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("subtopics", "roles", "companies")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip()[:200] for value in values if value.strip()))

    @model_validator(mode="after")
    def validate_question_card_structure(self) -> "KnowledgeUnit":
        if self.unit_type == "question_card":
            required = {"question", "reference_answer", "competencies", "interviewer_intent"}
            missing = sorted(required - self.metadata.keys())
            if missing:
                raise ValueError(f"question_card metadata is missing: {', '.join(missing)}")
        if self.unit_type == "user_evidence" and self.metadata.get("confirmed") is not True:
            raise ValueError("user_evidence must be explicitly confirmed")
        return self


class SourceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source_id: str
    path: str
    media_type: str
    content: str
    content_hash: str
    updated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RawKnowledgeUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_type: KnowledgeUnitType
    title: str
    content: str
    source_path: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    domain: str | None = Field(default=None, max_length=100)
    roles: list[str] = Field(default_factory=list, max_length=20)
    companies: list[str] = Field(default_factory=list, max_length=20)
    topics: list[str] = Field(default_factory=list, max_length=30)
    unit_types: list[KnowledgeUnitType] = Field(default_factory=list)
    difficulty: Literal["introductory", "intermediate", "advanced", "expert"] | None = None
    question_type: str | None = Field(default=None, max_length=100)
    scopes: list[KnowledgeScope] = Field(default_factory=lambda: ["public"])
    user_id: str = Field(default="local", min_length=1, max_length=200)
    session_id: str | None = Field(default=None, max_length=200)
    exclude_unit_ids: list[str] = Field(default_factory=list, max_length=200)
    source_ids: list[str] = Field(default_factory=list, max_length=100)
    top_k: int = Field(default=8, ge=1, le=50)

    @model_validator(mode="after")
    def validate_private_scope_context(self) -> "KnowledgeQuery":
        if "session" in self.scopes and not self.session_id:
            raise ValueError("session_id is required when session scope is requested")
        return self


class RetrievalHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit: KnowledgeUnit
    score: float = Field(ge=0, le=1)
    lexical_score: float = Field(default=0, ge=0, le=1)
    semantic_score: float = Field(default=0, ge=0, le=1)
    rerank_score: float = Field(default=0, ge=0, le=1)
    matched_terms: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    query: KnowledgeQuery
    hits: list[RetrievalHit] = Field(default_factory=list)
    total_candidates: int = Field(ge=0)
    truncated: bool = False
    retrieval_ms: float = Field(ge=0)
    index_version: str
    as_of: datetime
    warnings: list[str] = Field(default_factory=list)


class InterviewBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_role: str = ""
    seniority: str | None = None
    company: str | None = None
    competency_weights: dict[str, float] = Field(default_factory=dict)
    evidence_by_competency: dict[str, list[str]] = Field(default_factory=dict)
    gaps: list[str] = Field(default_factory=list)
    question_mix: dict[str, float] = Field(default_factory=dict)
    difficulty_path: list[Literal["introductory", "intermediate", "advanced", "expert"]] = Field(default_factory=list)
    covered_topics: list[str] = Field(default_factory=list)
    weak_topics: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
