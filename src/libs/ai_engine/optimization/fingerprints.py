from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def document_fingerprint(value: Any) -> str:
    normalized = canonical_json(value) if not isinstance(value, str) else re.sub(r"\s+", " ", value).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def section_fingerprints(sections: dict[str, Any]) -> dict[str, str]:
    return {name: document_fingerprint(value) for name, value in sorted(sections.items())}


def changed_sections(previous: dict[str, str], current: dict[str, str]) -> set[str]:
    return {name for name in previous.keys() | current.keys() if previous.get(name) != current.get(name)}

