from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from backend.services.interview_knowledge_service import InterviewKnowledgeService


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN = ROOT / "tests" / "fixtures" / "interview_knowledge" / "golden_queries.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "interview-knowledge-retrieval-evaluation.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate K1 retrieval without persisting third-party content.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--min-recall", type=float, default=0.55)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.exists():
        raise SystemExit("source file does not exist")

    golden = json.loads(args.golden.read_text(encoding="utf-8"))["cases"]
    with tempfile.TemporaryDirectory(prefix="buping-knowledge-eval-") as directory:
        temp = Path(directory)
        source_root = source.parent
        service = InterviewKnowledgeService(temp / "knowledge.sqlite3", source_root)
        source_type = "git" if source.is_dir() else "json"
        sync = service.sync({
            "id": "evaluation-source", "name": "ephemeral evaluation source",
            "source_type": source_type, "location": source.name,
            "scope": "user", "owner_id": "evaluation", "domain_pack": "ai_agent",
        }, accept_warnings=True)
        cases = []
        matched_terms = total_terms = 0
        for case in golden:
            result = service.search({
                "text": case["query"], "scopes": ["user"], "user_id": "evaluation",
                "top_k": args.top_k,
            })
            searchable = "\n".join(
                f"{hit['unit']['title']}\n{hit['unit']['content']}" for hit in result["hits"]
            ).casefold()
            expected = [str(term).casefold() for term in case["expected_terms"]]
            matched = [term for term in expected if term in searchable]
            matched_terms += len(matched)
            total_terms += len(expected)
            cases.append({
                "id": case["id"], "expected_terms": expected, "matched_terms": matched,
                "hit_count": len(result["hits"]), "retrieval_ms": result["retrieval_ms"],
            })
        recall = matched_terms / total_terms if total_terms else 1.0
        report = {
            "schema_version": "1", "source_content_persisted": False,
            "imported_units": sync["created"], "case_count": len(cases), "top_k": args.top_k,
            "term_recall_at_k": recall, "minimum_recall": args.min_recall, "cases": cases,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "imported_units", "case_count", "top_k", "term_recall_at_k", "minimum_recall",
    )}, ensure_ascii=False))
    if args.check and recall < args.min_recall:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
