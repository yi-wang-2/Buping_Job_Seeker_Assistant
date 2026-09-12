from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PublicKnowledgeSourceSpec(BaseModel):
    """A reviewed, version-pinned public source that users may install locally."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,79}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    repository_url: str = Field(min_length=1, max_length=2000)
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_type: Literal["git"] = "git"
    domain_pack: str = Field(min_length=1, max_length=100)
    license: str = Field(min_length=1, max_length=100)
    license_notice: str = Field(min_length=1, max_length=1000)
    license_evidence_path: str = Field(min_length=1, max_length=500)
    license_evidence_text: str = Field(min_length=1, max_length=200)
    required_paths: list[str] = Field(min_length=1, max_length=20)
    accept_import_warnings: bool = False

    @field_validator("repository_url")
    @classmethod
    def require_https_repository(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("public knowledge repository must use HTTPS")
        return value

    @field_validator("license_evidence_path")
    @classmethod
    def validate_evidence_path(cls, value: str) -> str:
        return cls._relative_path(value)

    @field_validator("required_paths")
    @classmethod
    def validate_required_paths(cls, values: list[str]) -> list[str]:
        return [cls._relative_path(value) for value in values]

    @staticmethod
    def _relative_path(value: str) -> str:
        path = PurePosixPath(value.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("catalog paths must be relative and cannot escape the source")
        return path.as_posix()


class PublicKnowledgeCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    sources: list[PublicKnowledgeSourceSpec] = Field(default_factory=list)

    @field_validator("sources")
    @classmethod
    def require_unique_ids(
        cls, values: list[PublicKnowledgeSourceSpec],
    ) -> list[PublicKnowledgeSourceSpec]:
        ids = [item.id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("public knowledge catalog contains duplicate source ids")
        return values

    def get(self, source_id: str) -> PublicKnowledgeSourceSpec:
        for source in self.sources:
            if source.id == source_id:
                return source
        raise KeyError("public knowledge source does not exist in the catalog")


def load_public_knowledge_catalog(path: str | Path) -> PublicKnowledgeCatalog:
    manifest = Path(path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    return PublicKnowledgeCatalog.model_validate(payload)
