from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable


def normalize_question(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold(), flags=re.UNICODE)


def evaluate_no_rag_cases(cases: Iterable[dict[str, Any]]) -> dict[str, Any]:
    case_results = []
    total_questions = 0
    duplicate_questions = 0
    covered_topics = 0
    expected_topics = 0
    total_tokens = 0
    total_latency_ms = 0.0

    for case in cases:
        questions = [str(item).strip() for item in case.get("questions", []) if str(item).strip()]
        normalized = [normalize_question(item) for item in questions]
        counts = Counter(normalized)
        duplicates = sum(count - 1 for count in counts.values() if count > 1)
        expected = {str(item).strip().casefold() for item in case.get("expected_topics", []) if str(item).strip()}
        covered = {str(item).strip().casefold() for item in case.get("covered_topics", []) if str(item).strip()}
        matched = len(expected & covered)
        coverage = matched / len(expected) if expected else 1.0
        result = {
            "id": case["id"],
            "question_count": len(questions),
            "duplicate_count": duplicates,
            "repeat_rate": duplicates / len(questions) if questions else 0.0,
            "topic_coverage": coverage,
            "input_tokens": int(case.get("input_tokens", 0)),
            "output_tokens": int(case.get("output_tokens", 0)),
            "latency_ms": float(case.get("latency_ms", 0)),
        }
        case_results.append(result)
        total_questions += len(questions)
        duplicate_questions += duplicates
        expected_topics += len(expected)
        covered_topics += matched
        total_tokens += result["input_tokens"] + result["output_tokens"]
        total_latency_ms += result["latency_ms"]

    count = len(case_results)
    return {
        "schema_version": "1",
        "mode": "no_rag",
        "case_count": count,
        "question_count": total_questions,
        "repeat_rate": duplicate_questions / total_questions if total_questions else 0.0,
        "topic_coverage": covered_topics / expected_topics if expected_topics else 1.0,
        "average_tokens": total_tokens / count if count else 0.0,
        "average_latency_ms": total_latency_ms / count if count else 0.0,
        "cases": case_results,
    }
