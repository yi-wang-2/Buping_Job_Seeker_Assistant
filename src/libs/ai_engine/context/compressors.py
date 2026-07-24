from __future__ import annotations

import re


def normalize_text(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def deduplicate_blocks(text: str) -> str:
    seen: set[str] = set()
    result: list[str] = []
    for raw_block in re.split(r"\n\s*\n+", text):
        block = normalize_text(raw_block)
        fingerprint = re.sub(r"\s+", " ", block).casefold()
        if fingerprint and fingerprint not in seen:
            seen.add(fingerprint)
            result.append(block)
    return "\n\n".join(result)


def truncate_semantic_blocks(text: str, max_tokens: int, token_count) -> str:
    if token_count(text) <= max_tokens:
        return text
    blocks = re.split(r"(?=^#{1,6}\s)|\n{2,}", text, flags=re.MULTILINE)
    kept: list[str] = []
    used = 0
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        cost = token_count(block)
        if used + cost > max_tokens:
            continue
        kept.append(block)
        used += cost
    return "\n\n".join(kept)
