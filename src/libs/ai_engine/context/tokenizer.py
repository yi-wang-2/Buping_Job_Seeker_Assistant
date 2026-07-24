from __future__ import annotations

import re
from typing import Protocol


class TokenEstimator(Protocol):
    def count(self, text: str) -> int: ...


class ConservativeTokenEstimator:
    """Dependency-free upper-bound estimate suitable for mixed Chinese/English."""

    _cjk = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
    _word = re.compile(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]")

    def count(self, text: str) -> int:
        if not text:
            return 0
        cjk_count = len(self._cjk.findall(text))
        remainder = self._cjk.sub(" ", text)
        other_units = len(self._word.findall(remainder))
        return max(1, cjk_count + other_units)

