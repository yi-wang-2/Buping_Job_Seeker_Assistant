from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from backend.services.interview_knowledge_service import get_interview_knowledge_service


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Import the local agent-interview-hub checkout.")
    parser.add_argument("--location", default="agent-interview-hub")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--accept-warnings", action="store_true")
    args = parser.parse_args()
    payload = {
        "id": "agent-interview-hub",
        "name": "AI Agent 面试知识库",
        "source_type": "git",
        "location": args.location,
        "scope": "public",
        "license": "MIT",
        "domain_pack": "ai_agent",
    }
    service = get_interview_knowledge_service()
    preview = service.preview(payload)
    print(json.dumps({
        key: preview[key] for key in (
            "source_id", "document_count", "unit_count", "duplicate_count",
            "rejected_count", "warnings", "sample_units",
        )
    }, ensure_ascii=False, indent=2))
    if args.preview:
        return 0
    result = service.sync(payload, accept_warnings=args.accept_warnings)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
