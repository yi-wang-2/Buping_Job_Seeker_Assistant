from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup


@dataclass(frozen=True, slots=True)
class ResolvedResumeArtifact:
    artifact_id: str
    version: str
    text: str
    source: str
    is_dirty: bool
    section_count: int
    blocks: tuple["ResumeArtifactBlock", ...]


@dataclass(frozen=True, slots=True)
class ResumeArtifactBlock:
    block_id: str
    section: str
    text: str


class ResumeArtifactResolver:
    """Resolve the browser's current resume artifact only after routing selects a body-reading Skill."""

    MAX_RAW_CHARACTERS = 1_500_000
    MAX_TEXT_CHARACTERS = 60_000

    def metadata(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        raw = snapshot.get("resume_artifact")
        if not isinstance(raw, dict):
            return {"artifact_id": "resume.current", "content_available": False}
        content = raw.get("content")
        return {
            "artifact_id": str(raw.get("id") or "resume.current")[:120],
            "version": str(raw.get("version") or "unsaved")[:120],
            "source": str(raw.get("source") or "workspace")[:40],
            "is_dirty": bool(raw.get("is_dirty")),
            "content_format": str(raw.get("content_format") or "html")[:20],
            "content_available": isinstance(content, str) and bool(content.strip()),
        }

    def resolve(self, snapshot: dict[str, Any]) -> ResolvedResumeArtifact:
        raw = snapshot.get("resume_artifact")
        if not isinstance(raw, dict):
            raise ValueError("当前工作区没有可读取的简历，请先加载或生成简历")
        content = raw.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("当前简历正文为空，请先加载或生成简历")
        if len(content) > self.MAX_RAW_CHARACTERS:
            raise ValueError("当前简历内容过大，无法安全分析")
        content_format = str(raw.get("content_format") or "html").lower()
        text, blocks = (
            self._from_html(content) if content_format == "html" else self._from_text(content)
        )
        if not text:
            raise ValueError("当前简历没有可分析的正文")
        limited_blocks = self._limit_blocks(blocks, self.MAX_TEXT_CHARACTERS)
        return ResolvedResumeArtifact(
            artifact_id=str(raw.get("id") or "resume.current"),
            version=str(raw.get("version") or "unsaved"),
            text=text[: self.MAX_TEXT_CHARACTERS],
            source=str(raw.get("source") or "workspace"),
            is_dirty=bool(raw.get("is_dirty")),
            section_count=len(blocks),
            blocks=limited_blocks,
        )

    @classmethod
    def _from_html(cls, content: str) -> tuple[str, tuple[ResumeArtifactBlock, ...]]:
        soup = BeautifulSoup(content, "html.parser")
        for node in soup.select(
            "script,style,noscript,svg,template,.editor-toolbar,.editor-controls,"
            ".page-break-guide,.preview-only-hint,[data-editor-only]"
        ):
            node.decompose()
        text = cls._clean(soup.get_text("\n"))
        blocks: list[ResumeArtifactBlock] = []
        header = soup.select_one("body > header, body > h1, .resume-header")
        if header:
            header_text = cls._clean(header.get_text("\n"))
            if header_text:
                blocks.append(ResumeArtifactBlock("resume-header", "基本信息", header_text))
        for index, section in enumerate(soup.select("section"), 1):
            heading = section.select_one("h1,h2,h3")
            section_name = cls._clean(heading.get_text(" ")) if heading else f"模块 {index}"
            raw_id = str(section.get("id") or section.get("data-source-id") or f"section-{index}")
            block_id = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", raw_id).strip("-") or f"section-{index}"
            block_text = cls._clean(section.get_text("\n"))
            if block_text:
                blocks.append(ResumeArtifactBlock(block_id, section_name, block_text))
        if not blocks:
            blocks.append(ResumeArtifactBlock("resume-document", "整份简历", text))
        return text, tuple(blocks)

    @classmethod
    def _from_text(cls, content: str) -> tuple[str, tuple[ResumeArtifactBlock, ...]]:
        text = cls._clean(content)
        return text, (ResumeArtifactBlock("resume-document", "整份简历", text),)

    @staticmethod
    def _clean(content: str) -> str:
        lines = [re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in content.splitlines()]
        return "\n".join(line for line in lines if line)

    @staticmethod
    def _limit_blocks(
        blocks: tuple[ResumeArtifactBlock, ...], limit: int,
    ) -> tuple[ResumeArtifactBlock, ...]:
        remaining = limit
        limited: list[ResumeArtifactBlock] = []
        for block in blocks:
            if remaining <= 0:
                break
            text = block.text[:remaining]
            if text:
                limited.append(ResumeArtifactBlock(block.block_id, block.section, text))
                remaining -= len(text)
        return tuple(limited)
