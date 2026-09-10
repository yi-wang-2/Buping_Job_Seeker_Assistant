from __future__ import annotations

import re

from ..presentation import FollowUpBlock, HeadingBlock, ParagraphBlock, ResponseDocument
from .models import SupervisorTurn


class AssistantTurnPresenter:
    """Map a direct Supervisor response to the shared presentation protocol."""

    @staticmethod
    def present(turn: SupervisorTurn) -> ResponseDocument:
        response = (turn.response or "已完成。").strip()
        blocks = []
        # The Supervisor is asked to return Markdown, but a deterministic heading
        # keeps provider fallbacks and older responses inside the same visual contract.
        if not re.match(r"^\s{0,3}#{1,6}\s+", response):
            blocks.append(HeadingBlock(
                "需要补充的信息" if turn.kind == "clarification" else "回答"
            ))
        blocks.append(ParagraphBlock(response))
        if turn.follow_up.strip():
            blocks.append(FollowUpBlock(turn.follow_up))
        return ResponseDocument(tuple(blocks))
