from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from typing import Any

from backend.services.job_radar_service import DATA_DIR
from src.libs.ai_engine.knowledge import (
    HashingEmbeddingProvider,
    HybridKnowledgeRetriever,
    KnowledgeQuery,
    KnowledgeRegistry,
    KnowledgeSource,
    SQLiteKnowledgeRepository,
    SQLiteVectorIndex,
)
from src.libs.ai_engine.knowledge.adapters import (
    ArchiveAdapter, DocxAdapter, GitSourceAdapter, JSONAdapter, LocalFileAdapter,
    MarkdownAdapter, PDFAdapter, UploadAdapter,
)


KNOWLEDGE_ROOT = DATA_DIR / "knowledge_sources"
KNOWLEDGE_DB = DATA_DIR / "interview_knowledge.sqlite3"


class InterviewKnowledgeService:
    def __init__(self, db_path: Path = KNOWLEDGE_DB, source_root: Path = KNOWLEDGE_ROOT) -> None:
        self.source_root = source_root.resolve()
        self.source_root.mkdir(parents=True, exist_ok=True)
        self.repository = SQLiteKnowledgeRepository(db_path)
        self.registry = KnowledgeRegistry(self.repository)
        for source_type, adapter in {
            "local_file": LocalFileAdapter(), "markdown": MarkdownAdapter(),
            "json": JSONAdapter(), "git": GitSourceAdapter(),
            "pdf": PDFAdapter(), "docx": DocxAdapter(), "archive": ArchiveAdapter(),
            "upload": UploadAdapter(),
        }.items():
            self.registry.register_adapter(source_type, adapter)
        self.vector_index = SQLiteVectorIndex(self.repository, HashingEmbeddingProvider())
        self.retriever = HybridKnowledgeRetriever(self.repository, self.vector_index)

    def _location(self, location: str) -> Path:
        candidate = (self.source_root / location).resolve()
        if candidate != self.source_root and self.source_root not in candidate.parents:
            raise ValueError("knowledge source must stay inside data_folder/knowledge_sources")
        if not candidate.exists():
            raise ValueError("knowledge source does not exist")
        return candidate

    def build_source(self, payload: dict[str, Any]) -> KnowledgeSource:
        location = self._location(str(payload.get("location") or ""))
        scope = str(payload.get("scope") or "public")
        license_name = str(payload.get("license") or "").strip() or None
        if scope == "public" and not license_name:
            raise ValueError("a license identifier is required for public knowledge")
        return KnowledgeSource(
            id=str(payload.get("id") or "").strip(),
            name=str(payload.get("name") or "").strip(),
            source_type=payload.get("source_type", "local_file"),
            location=str(location), scope=scope, owner_id=payload.get("owner_id"),
            license=license_name, domain_pack=payload.get("domain_pack") or "interview",
            created_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = Path(filename or "knowledge").name
        stem = re.sub(r"[^\w.-]+", "_", Path(name).stem, flags=re.UNICODE).strip("._") or "knowledge"
        return f"{stem[:80]}{Path(name).suffix.lower()}"

    def save_upload(
        self, *, filename: str, content: bytes, user_id: str = "local",
        session_id: str | None = None, domain_pack: str = "interview",
    ) -> dict[str, Any]:
        if not content:
            raise ValueError("uploaded knowledge file is empty")
        if len(content) > 10 * 1024 * 1024:
            raise ValueError("uploaded knowledge file exceeds 10 MB")
        safe_name = self._safe_filename(filename)
        suffix = Path(safe_name).suffix.lower()
        source_type = {
            ".md": "markdown", ".markdown": "markdown", ".json": "json",
            ".pdf": "pdf", ".docx": "docx", ".zip": "archive",
        }.get(suffix)
        if not source_type:
            raise ValueError("supported knowledge files: Markdown, JSON, PDF, DOCX and ZIP")
        source_id = f"user-{hashlib.sha256(content).hexdigest()[:20]}"
        folder = self.source_root / "uploads" / re.sub(r"[^\w.-]+", "_", user_id)[:80]
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{source_id}-{safe_name}"
        created_file = not path.exists()
        path.write_bytes(content)
        owner_id = session_id if session_id else user_id
        scope = "session" if session_id else "user"
        payload = {
            "id": source_id, "name": Path(safe_name).stem, "source_type": source_type,
            "location": path.relative_to(self.source_root).as_posix(), "scope": scope,
            "owner_id": owner_id, "domain_pack": domain_pack,
        }
        try:
            preview = self.preview(payload)
            synced = self.sync(payload, accept_warnings=False)
        except Exception:
            # A rejected upload must not leave private or malformed source files
            # behind. Preserve a pre-existing identical upload, if any.
            if created_file:
                path.unlink(missing_ok=True)
            raise
        return {"source": self.repository.get_source(source_id).model_dump(mode="json"),
                "preview": preview, "sync": synced}

    def preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        preview = self.registry.preview(self.build_source(payload))
        return preview.model_dump(mode="json", exclude={"units"}) | {
            "sample_units": [unit.model_dump(mode="json") for unit in preview.units[:10]],
            "sample_truncated": len(preview.units) > 10,
        }

    def sync(self, payload: dict[str, Any], *, accept_warnings: bool = False) -> dict[str, Any]:
        source = self.build_source(payload)
        preview = self.registry.preview(source)
        result = self.registry.sync(source, accept_warnings=accept_warnings)
        vector_stats = self.vector_index.index_units(preview.units)
        return {**result, "vectors": vector_stats}

    def search(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.retriever.retrieve(KnowledgeQuery.model_validate(payload))
        return result.model_dump(mode="json")

    def list_sources(self, user_id: str = "local", session_id: str | None = None) -> list[dict[str, Any]]:
        return [
            source.model_dump(mode="json") | {"stats": self.repository.source_stats(source.id)}
            for source in self.repository.list_sources(user_id=user_id, session_id=session_id)
        ]

    def set_enabled(self, source_id: str, enabled: bool, *, user_id: str = "local") -> dict[str, Any]:
        source = self.repository.get_source(source_id)
        if source is None:
            raise KeyError("knowledge source does not exist")
        if source.scope != "public" and source.owner_id != user_id:
            raise PermissionError("knowledge source does not belong to the current user")
        return self.repository.set_source_status(
            source_id, "ready" if enabled else "disabled",
        ).model_dump(mode="json")

    def delete_source(self, source_id: str, *, user_id: str = "local") -> bool:
        source = self.repository.get_source(source_id)
        if source is None:
            return False
        if source.scope != "public" and source.owner_id != user_id:
            raise PermissionError("knowledge source does not belong to the current user")
        deleted = self.repository.delete_source(source_id)
        if deleted and source.scope in {"user", "session"}:
            path = Path(source.location).resolve()
            if self.source_root == path or self.source_root in path.parents:
                path.unlink(missing_ok=True)
        return deleted


_service: InterviewKnowledgeService | None = None


def get_interview_knowledge_service() -> InterviewKnowledgeService:
    global _service
    if _service is None:
        _service = InterviewKnowledgeService()
    return _service
