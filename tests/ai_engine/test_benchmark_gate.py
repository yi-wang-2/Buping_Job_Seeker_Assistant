from pathlib import Path

from scripts.benchmark_ai_engine import check_budgets, run_benchmarks


def test_ai_engine_performance_budgets():
    report = run_benchmarks()
    budgets = Path("tests/fixtures/ai_engine/performance_budgets.json")

    assert check_budgets(report, budgets) == []

