from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any
import uuid

from backend.services.job_radar_service import DATA_DIR
from src.libs.ai_engine.knowledge import (
    HashingEmbeddingProvider,
    HybridKnowledgeRetriever,
    KnowledgeQuery,
    KnowledgeRegistry,
    KnowledgeSource,
    PublicKnowledgeCatalog,
    PublicKnowledgeSourceSpec,
    SQLiteKnowledgeRepository,
    SQLiteVectorIndex,
    load_public_knowledge_catalog,
)
from src.libs.ai_engine.knowledge.adapters import (
    ArchiveAdapter, DocxAdapter, GitSourceAdapter, JSONAdapter, LocalFileAdapter,
    MarkdownAdapter, PDFAdapter, UploadAdapter,
)


KNOWLEDGE_ROOT = DATA_DIR / "knowledge_sources"
KNOWLEDGE_DB = DATA_DIR / "interview_knowledge.sqlite3"
KNOWLEDGE_CATALOG = Path(__file__).resolve().parents[2] / "assets" / "interview_knowledge_sources.json"
MAX_CATALOG_FILES = 20_000
MAX_CATALOG_BYTES = 250 * 1024 * 1024


class InterviewKnowledgeService:
    def __init__(
        self, db_path: Path = KNOWLEDGE_DB, source_root: Path = KNOWLEDGE_ROOT,
        catalog_path: Path = KNOWLEDGE_CATALOG,
    ) -> None:
        self.source_root = source_root.resolve()
        self.source_root.mkdir(parents=True, exist_ok=True)
        self.catalog: PublicKnowledgeCatalog = load_public_knowledge_catalog(catalog_path)
        self.catalog_source_root = self.source_root / "public"
        self.catalog_state_root = self.source_root / ".catalog"
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

    def _catalog_target(self, source_id: str) -> Path:
        spec = self.catalog.get(source_id)
        target = (self.catalog_source_root / spec.id).resolve()
        root = self.catalog_source_root.resolve()
        if root not in target.parents:
            raise ValueError("catalog source path escapes the knowledge root")
        return target

    def _catalog_state_path(self, source_id: str) -> Path:
        self.catalog.get(source_id)
        return self.catalog_state_root / f"{source_id}.json"

    def _read_catalog_state(self, source_id: str) -> dict[str, Any]:
        path = self._catalog_state_path(source_id)
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_catalog_state(self, spec: PublicKnowledgeSourceSpec) -> None:
        self.catalog_state_root.mkdir(parents=True, exist_ok=True)
        self._catalog_state_path(spec.id).write_text(json.dumps({
            "source_id": spec.id, "revision": spec.revision,
            "repository_url": spec.repository_url,
            "installed_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _run_git(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        try:
            return subprocess.run(
                ["git", *arguments], check=True, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=180, env=env,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("Git is required to install this public knowledge source") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("public knowledge source download timed out") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "Git command failed").strip()
            raise RuntimeError(f"public knowledge source download failed: {detail[-1000:]}") from exc

    def _validate_catalog_checkout(self, spec: PublicKnowledgeSourceSpec, path: Path) -> None:
        root = path.resolve()
        file_count = total_bytes = 0
        for candidate in path.rglob("*"):
            relative = candidate.relative_to(path)
            if ".git" in relative.parts:
                continue
            if candidate.is_symlink():
                raise ValueError(f"downloaded knowledge source contains a symbolic link: {relative}")
            if candidate.is_file():
                resolved = candidate.resolve()
                if root not in resolved.parents:
                    raise ValueError("downloaded knowledge source contains an unsafe file path")
                file_count += 1
                total_bytes += candidate.stat().st_size
                if file_count > MAX_CATALOG_FILES or total_bytes > MAX_CATALOG_BYTES:
                    raise ValueError("downloaded knowledge source exceeds the local safety limit")
        for relative in spec.required_paths:
            if not (path / relative).is_file():
                raise ValueError(f"downloaded knowledge source is missing required file: {relative}")
        evidence_path = path / spec.license_evidence_path
        try:
            evidence = evidence_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise ValueError("downloaded knowledge source has no verifiable license evidence") from exc
        if spec.license_evidence_text.casefold() not in evidence.casefold():
            raise ValueError("downloaded knowledge source license evidence does not match the catalog")

    def _checkout_catalog_source(self, spec: PublicKnowledgeSourceSpec, destination: Path) -> None:
        self._run_git(["init", str(destination)])
        self._run_git(["-C", str(destination), "remote", "add", "origin", spec.repository_url])
        self._run_git(["-C", str(destination), "fetch", "--depth", "1", "origin", spec.revision])
        self._run_git(["-C", str(destination), "checkout", "--detach", "FETCH_HEAD"])
        actual = self._run_git(["-C", str(destination), "rev-parse", "HEAD"]).stdout.strip().lower()
        if actual != spec.revision:
            raise ValueError("downloaded knowledge source revision does not match the catalog")
        self._validate_catalog_checkout(spec, destination)
        shutil.rmtree(destination / ".git", ignore_errors=True)

    def _catalog_source_payload(self, spec: PublicKnowledgeSourceSpec) -> dict[str, Any]:
        target = self._catalog_target(spec.id)
        return {
            "id": spec.id, "name": spec.name, "source_type": spec.source_type,
            "location": target.relative_to(self.source_root).as_posix(),
            "scope": "public", "license": spec.license, "domain_pack": spec.domain_pack,
        }

    def list_catalog(self) -> list[dict[str, Any]]:
        items = []
        for spec in self.catalog.sources:
            target = self._catalog_target(spec.id)
            state = self._read_catalog_state(spec.id)
            source = self.repository.get_source(spec.id)
            source_path = Path(source.location).resolve() if source else None
            installed = bool(source and source_path and source_path.exists())
            managed_copy = bool(installed and target.is_dir() and source_path == target)
            installed_revision = str(state.get("revision") or "")
            items.append({
                **spec.model_dump(exclude={"accept_import_warnings"}),
                "installed": installed,
                "managed_copy": managed_copy,
                "installed_revision": installed_revision or None,
                "update_available": bool(installed and (
                    not managed_copy or installed_revision != spec.revision
                )),
                "sync_status": source.sync_status if installed and source else "not_installed",
                "stats": self.repository.source_stats(spec.id) if installed else {
                    "units": 0, "characters": 0, "average_quality": 0,
                },
            })
        return items

    def install_catalog_source(
        self, source_id: str, *, accept_license: bool,
    ) -> dict[str, Any]:
        spec = self.catalog.get(source_id)
        if not accept_license:
            raise ValueError("license acceptance is required before installing public knowledge")
        target = self._catalog_target(source_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{source_id}-install-", dir=target.parent))
        backup = target.parent / f".{source_id}-backup-{uuid.uuid4().hex}"
        moved_existing = False
        try:
            self._checkout_catalog_source(spec, temporary)
            if target.exists():
                target.replace(backup)
                moved_existing = True
            temporary.replace(target)
            try:
                result = self.sync(
                    self._catalog_source_payload(spec),
                    accept_warnings=spec.accept_import_warnings,
                )
            except Exception:
                shutil.rmtree(target, ignore_errors=True)
                if moved_existing and backup.exists():
                    backup.replace(target)
                raise
            self._write_catalog_state(spec)
            return {
                "source": self.repository.get_source(source_id).model_dump(mode="json"),
                "sync": result, "catalog": next(
                    item for item in self.list_catalog() if item["id"] == source_id
                ),
            }
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
            shutil.rmtree(backup, ignore_errors=True)

    def rebuild_catalog_source(self, source_id: str) -> dict[str, Any]:
        spec = self.catalog.get(source_id)
        target = self._catalog_target(source_id)
        if not target.is_dir():
            raise ValueError("public knowledge source is not installed")
        self._validate_catalog_checkout(spec, target)
        result = self.sync(
            self._catalog_source_payload(spec),
            accept_warnings=spec.accept_import_warnings,
        )
        self._write_catalog_state(spec)
        return {
            "source": self.repository.get_source(source_id).model_dump(mode="json"),
            "sync": result,
        }

    def uninstall_catalog_source(self, source_id: str) -> bool:
        target = self._catalog_target(source_id)
        state_path = self._catalog_state_path(source_id)
        source = self.repository.get_source(source_id)
        paths = {target}
        if source:
            source_path = Path(source.location).resolve()
            root = self.source_root.resolve()
            if source_path != root and root in source_path.parents:
                paths.add(source_path)
        if not any(path.exists() for path in paths) and not state_path.exists() and source is None:
            return False
        self.repository.delete_source(source_id)
        for path in paths:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.is_file():
                path.unlink(missing_ok=True)
        state_path.unlink(missing_ok=True)
        return True

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
