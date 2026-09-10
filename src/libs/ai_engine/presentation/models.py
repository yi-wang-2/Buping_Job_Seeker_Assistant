from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HeadingBlock:
    text: str
    level: int = 3


@dataclass(frozen=True, slots=True)
class ParagraphBlock:
    text: str


@dataclass(frozen=True, slots=True)
class CalloutBlock:
    """Visually emphasize a summary, decision, warning, or other key message."""

    text: str


@dataclass(frozen=True, slots=True)
class DetailItem:
    title: str
    label: str = ""
    body: str = ""
    quote: str = ""


@dataclass(frozen=True, slots=True)
class DetailListBlock:
    items: tuple[DetailItem, ...]
    ordered: bool = True


@dataclass(frozen=True, slots=True)
class FollowUpBlock:
    prompt: str


ContentBlock = HeadingBlock | ParagraphBlock | CalloutBlock | DetailListBlock | FollowUpBlock


@dataclass(frozen=True, slots=True)
class ResponseDocument:
    blocks: tuple[ContentBlock, ...]
