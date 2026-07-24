from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from ..models import LLMRequest, LLMResponse


class TraceSink(Protocol):
    def record(
        self,
        trace_id: str,
        request: LLMRequest,
        *,
        response: LLMResponse | None = None,
        error: Exception | None = None,
        retries: int = 0,
    ) -> None: ...


class JsonlTraceSink:
    """Metadata-only JSONL trace sink; prompts, responses and secrets are excluded."""

    def __init__(self, path: str | Path = "data_folder/output/ai_usage.jsonl") -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def record(
        self,
        trace_id: str,
        request: LLMRequest,
        *,
        response: LLMResponse | None = None,
        error: Exception | None = None,
        retries: int = 0,
    ) -> None:
        event = {
            "trace_id": trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": request.provider,
            "model": request.model,
            "skill": request.metadata.get("skill", ""),
            "status": "success" if response else "error",
            "usage": {
                "input_tokens": response.usage.input_tokens if response else 0,
                "output_tokens": response.usage.output_tokens if response else 0,
                "total_tokens": response.usage.total_tokens if response else 0,
            },
            "latency_ms": response.latency_ms if response else 0,
            "retries": response.retries if response else retries,
            "error_type": type(error).__name__ if error else "",
            "context": {
                "original_tokens": int(request.metadata.get("context_original_tokens", 0)),
                "final_tokens": int(request.metadata.get("context_final_tokens", 0)),
                "items_kept": int(request.metadata.get("context_items_kept", 0)),
                "items_compressed": int(request.metadata.get("context_items_compressed", 0)),
                "items_dropped": int(request.metadata.get("context_items_dropped", 0)),
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

