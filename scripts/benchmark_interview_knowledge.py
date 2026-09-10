from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.libs.ai_engine.knowledge.evaluation import evaluate_no_rag_cases


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "tests" / "fixtures" / "interview_knowledge" / "no_rag_baseline_cases.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "interview-knowledge-no-rag-baseline.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the repeatable Interview Knowledge K0 baseline.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = evaluate_no_rag_cases(payload.get("cases", []))
    if args.check and not result["case_count"]:
        raise SystemExit("baseline contains no cases")
    if args.check and result["question_count"] < result["case_count"]:
        raise SystemExit("every baseline case must include at least one question")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "case_count", "question_count", "repeat_rate", "topic_coverage",
        "average_tokens", "average_latency_ms",
    )}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
