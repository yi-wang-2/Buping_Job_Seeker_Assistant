from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnswerSignals:
    depth: float
    has_example: bool
    has_reasoning: bool
    has_tradeoff: bool
    has_result: bool
    decision: str


def evaluate_answer_signals(answer: str) -> AnswerSignals:
    """Cheap steering signals; final semantic scoring remains the LLM evaluator's job."""
    text = answer.strip().casefold()
    length_score = min(1.0, len(text) / 260)
    has_example = any(marker in text for marker in ("例如", "项目", "我负责", "example"))
    has_reasoning = any(marker in text for marker in ("因为", "所以", "原因", "therefore", "because"))
    has_tradeoff = any(marker in text for marker in ("取舍", "权衡", "代价", "trade-off", "tradeoff"))
    has_result = any(marker in text for marker in ("结果", "%", "ms", "提升", "降低", "result"))
    depth = min(1.0, length_score + .1 * sum((has_example, has_reasoning, has_tradeoff, has_result)))
    decision = "follow_up" if depth < .5 else "deepen" if depth < .8 else "switch_or_challenge"
    return AnswerSignals(round(depth, 3), has_example, has_reasoning, has_tradeoff, has_result, decision)
