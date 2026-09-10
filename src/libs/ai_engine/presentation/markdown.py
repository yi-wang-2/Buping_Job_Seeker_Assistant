from __future__ import annotations

from .models import (
    CalloutBlock,
    DetailListBlock,
    FollowUpBlock,
    HeadingBlock,
    ParagraphBlock,
    ResponseDocument,
)


class MarkdownRenderer:
    """Render the generic response document without knowing any Skill semantics."""

    @staticmethod
    def render(document: ResponseDocument) -> str:
        rendered: list[str] = []
        for block in document.blocks:
            if isinstance(block, HeadingBlock):
                level = max(1, min(6, block.level))
                rendered.append(f"{'#' * level} {block.text.strip()}")
            elif isinstance(block, ParagraphBlock):
                rendered.append(block.text.strip())
            elif isinstance(block, CalloutBlock):
                rendered.append("\n".join(
                    f"> {line}" if line.strip() else ">"
                    for line in block.text.strip().splitlines()
                ))
            elif isinstance(block, DetailListBlock):
                rendered.append(MarkdownRenderer._render_detail_list(block))
            elif isinstance(block, FollowUpBlock):
                rendered.append(f"---\n\n{block.prompt.strip()}")
            else:  # pragma: no cover - guarded by the ContentBlock type
                raise TypeError(f"Unsupported presentation block: {type(block).__name__}")
        return "\n\n".join(part for part in rendered if part)

    @staticmethod
    def _render_detail_list(block: DetailListBlock) -> str:
        rendered: list[str] = []
        for index, item in enumerate(block.items, 1):
            marker = f"{index}." if block.ordered else "-"
            heading = f"**{item.title.strip()}**"
            if item.label.strip():
                heading += f" · {item.label.strip()}"
            lines = [f"{marker} {heading}"]
            if item.body.strip():
                lines.extend(("", f"   {item.body.strip()}"))
            if item.quote.strip():
                quote_lines = item.quote.strip().splitlines()
                lines.extend(("", *[f"   > {line}" for line in quote_lines]))
            rendered.append("\n".join(lines))
        return "\n\n".join(rendered)
