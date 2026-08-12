"""Deterministic AI Engine functional/performance benchmark and regression gate."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.libs.ai_engine.context import BudgetAllocation, ContextItem, ContextKind, ContextManager, TokenBudgetAllocator
from src.libs.ai_engine.memory import MemoryItem, SQLiteMemoryRepository
from src.libs.ai_engine.models import LLMRequest, LLMResponse, Message, TokenUsage
from src.libs.ai_engine.optimization import PromptCache, changed_sections, section_fingerprints
from src.libs.ai_engine.providers import GatewayConfig, LLMGateway
from src.libs.ai_engine.harness import (
    evaluate_resume_candidate,
    generate_candidates,
    protect_hard_facts_in_place,
)
from src.libs.ai_engine.skills.builtin import (
    CareerAdvisorSkill, InterviewCoachSkill, JDAnalyzerSkill, JobStatusClassifierSkill, MockInterviewerSkill,
    ResumeWriterSkill, SkillMatcherSkill, TextRewriterSkill,
)

DEFAULT_BUDGETS = ROOT / "tests" / "fixtures" / "ai_engine" / "performance_budgets.json"


def percentile(values: list[float], value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * value + 0.9999) - 1))
    return ordered[index]


def timed(call: Callable[[], Any], repeats: int) -> tuple[list[float], Any]:
    durations: list[float] = []
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = call()
        durations.append((time.perf_counter() - started) * 1000)
    return durations, result


def benchmark_context() -> dict[str, float]:
    facts = ["公司：星海科技", "时间：2022-2024", "性能提升：35%", "用户规模：100万"]
    repeated = "\n\n".join(["负责 Python 服务开发并将接口延迟降低 35%。"] * 12)
    raw = "\n".join(facts) + "\n\n" + repeated
    manager = ContextManager()
    original_tokens = manager.estimator.count(raw)
    durations, bundle = timed(
        lambda: manager.build([
            ContextItem("facts", ContextKind.TASK, "\n".join(facts), "resume", protected=True, priority=100, relevance=1),
            ContextItem("details", ContextKind.TASK, repeated, "resume", priority=60, relevance=.8),
        ], BudgetAllocation(160, {"task": 160})),
        100,
    )
    final_text = "\n".join(item.content for item in bundle.items)
    retained = sum(fact in final_text for fact in facts)
    return {
        "token_reduction_percent": round((1 - bundle.total_tokens / original_tokens) * 100, 2),
        "fact_retention_percent": round(retained / len(facts) * 100, 2),
        "p95_latency_ms": round(percentile(durations, .95), 3),
        "original_tokens": original_tokens,
        "final_tokens": bundle.total_tokens,
    }


def benchmark_cache(path: Path) -> dict[str, float]:
    cache = PromptCache(path, max_items=16)
    response = LLMResponse("cached", "fake", "fake", TokenUsage(10, 2, 12))
    cache.put("benchmark", response)
    durations, _ = timed(lambda: cache.get("benchmark"), 100)
    hits = sum(cache.get("benchmark") is not None for _ in range(20))
    stats = cache.stats()
    return {
        "hit_rate_percent": round(hits / 20 * 100, 2),
        "p95_read_latency_ms": round(percentile(durations, .95), 3),
        "persistent_hits": stats["hits"],
        "entries": stats["entries"],
    }


def benchmark_memory(path: Path) -> dict[str, float]:
    repository = SQLiteMemoryRepository(path)
    index = 0

    def write():
        nonlocal index
        index += 1
        return repository.upsert_memory(MemoryItem(namespace="benchmark", key=f"key-{index}", value={"value": index}))

    write_durations, _ = timed(write, 50)
    read_durations, items = timed(lambda: repository.list_memories(namespace="benchmark"), 50)
    return {
        "records": len(items),
        "p95_write_latency_ms": round(percentile(write_durations, .95), 3),
        "p95_read_latency_ms": round(percentile(read_durations, .95), 3),
        "round_trip_percent": 100.0 if len(items) == 50 else round(len(items) / 50 * 100, 2),
    }


@dataclass
class FakeResponse:
    content: str = "ok"
    response_metadata: dict[str, Any] = None
    usage_metadata: dict[str, int] = None

    def __post_init__(self):
        self.response_metadata = {"model_name": "fake", "finish_reason": "stop"}
        self.usage_metadata = {"input_tokens": 8, "output_tokens": 2, "total_tokens": 10}


class FakeClient:
    def invoke(self, messages):
        return FakeResponse()


def benchmark_gateway() -> dict[str, float]:
    gateway = LLMGateway(GatewayConfig(max_retries=0), client_factory=lambda _: FakeClient())
    request = LLMRequest((Message("user", "benchmark"),), "fake", "fake", max_output_tokens=100)
    durations, response = timed(lambda: gateway.invoke(request), 200)
    return {
        "p95_overhead_ms": round(percentile(durations, .95), 3),
        "usage_accuracy_percent": 100.0 if response.usage == TokenUsage(8, 2, 10) else 0.0,
    }


def benchmark_skills_and_prompts() -> dict[str, Any]:
    prompts = {
        "zh": {"fix_grammar": "修正错误；只输出改写后的文本，不得虚构经历。"},
        "en": {"fix_grammar": "Fix errors. Output only rewritten text. Do not invent facts."},
    }
    skills = [
        TextRewriterSkill(prompts), JDAnalyzerSkill(), InterviewCoachSkill(), MockInterviewerSkill(),
        ResumeWriterSkill(), SkillMatcherSkill(), CareerAdvisorSkill(), JobStatusClassifierSkill(),
    ]
    sample_inputs = {
        "text_rewriter": {"text": "负责 Python 开发", "mode": "fix_grammar", "target_language": "zh"},
        "jd_analyzer": {"job_description": "招聘 Python 工程师，要求 3 年经验。"},
        "interview_coach": {
            "resume": "3 年 Python 经验", "job_description": "Python 工程师",
            "prepared_prompt": "# 第一部分：岗位分析\n\n简历：3 年 Python 经验\n\n# 第二部分：面试准备报告",
        },
        "mock_interviewer": {"resume": "3 年 Python 经验", "job_description": "Python 工程师", "history": []},
        "resume_writer": {"resume": "3 年 Python 经验"},
        "skill_matcher": {"resume": "3 年 Python 经验", "job_description": "Python 工程师"},
        "career_advisor": {"resume": "3 年 Python 经验"},
        "job_status_classifier": {
            "page_context": "测试公司 Python 工程师 当前状态：技术面试",
            "company": "测试公司", "role": "Python 工程师",
        },
    }
    manager = ContextManager()
    allocator = TokenBudgetAllocator()
    skill_metrics: list[dict[str, Any]] = []
    successful_executions = 0
    for skill in skills:
        started = time.perf_counter()
        inputs = sample_inputs[skill.metadata.name]
        try:
            skill.validate_input(inputs)
            bundle = manager.build(skill.context_items(inputs), allocator.allocate(skill.metadata.token_budget))
            messages = skill.build_messages(inputs, bundle.items)
            structured_outputs = {
                "jd_analyzer": '{"role":"Python 工程师","company":null,"responsibilities":[],"required_skills":["Python"],"preferred_skills":[],"experience_years":3,"education":null,"location":null,"salary":null,"keywords":["Python"]}',
                "skill_matcher": '{"match_score":80,"matched_skills":["Python"],"gaps":[],"evidence":[],"recommendations":[]}',
                "career_advisor": '{"summary":"继续提升 AI 能力","priorities":["项目"],"action_plan":["完善作品集"],"assumptions":[]}',
                "job_status_classifier": '{"matched_application":true,"normalized_status":"技术面","raw_status":"技术面试","confidence":0.95,"reason":"页面明确显示"}',
            }
            output = structured_outputs.get(skill.metadata.name, "符合约束的测试输出")
            parsed = skill.parse_output(LLMResponse(output, "fake", "fake", TokenUsage(10, 2, 12)))
            if skill.metadata.output_schema is not None:
                skill.metadata.output_schema.model_validate(parsed.structured_output)
            validator = getattr(skill, "validate_output", None)
            if callable(validator):
                validator(parsed, inputs)
            success = bool(parsed.content)
        except Exception:
            bundle = None
            messages = ()
            success = False
        successful_executions += int(success)
        skill_metrics.append({
            "skill": skill.metadata.name,
            "success": success,
            "context_tokens": bundle.total_tokens if bundle else 0,
            "message_count": len(messages),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        })
    unique_names = len({skill.metadata.name for skill in skills})
    valid_budgets = sum(skill.metadata.token_budget.available_input > 0 for skill in skills)
    source_files = [
        ROOT / "backend" / "services" / "resume_service.py",
        ROOT / "src" / "libs" / "ai_engine" / "skills" / "builtin" / "career_skills.py",
        ROOT / "src" / "libs" / "ai_engine" / "skills" / "builtin" / "jd_analyzer" / "skill.py",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    contracts = ["不得虚构", "只输出", "JSON", "证据", "不得新增"]
    contract_hits = sum(contract in source for contract in contracts)
    before = section_fingerprints({"education": "A", "experience": "B"})
    after = section_fingerprints({"education": "A", "experience": "C"})
    return {
        "registered_skills": len(skills),
        "unique_skill_names": unique_names,
        "valid_budget_percent": round(valid_budgets / len(skills) * 100, 2),
        "prompt_contract_coverage_percent": round(contract_hits / len(contracts) * 100, 2),
        "incremental_detection_percent": 100.0 if changed_sections(before, after) == {"experience"} else 0.0,
        "execution_success_percent": round(successful_executions / len(skills) * 100, 2),
        "by_skill": skill_metrics,
    }


def benchmark_resume_quality() -> dict[str, float]:
    resume = {
        "personal_information": {"name": "易", "surname": "旺", "email": "truth@example.com"},
        "education_details": [],
        "experience_details": [{
            "company": "事实公司", "position": "算法工程师", "location": "上海",
            "employment_period": "2023-2025",
            "key_responsibilities": [{"responsibility": "负责模型训练与部署"}],
            "skills_acquired": ["Python"],
        }],
        "projects": [{"name": "事实项目", "description": "完成检索服务建设", "link": ""}],
        "achievements": [], "certifications": [], "languages": [], "interests": [],
    }
    shared = {
        "header": "<header><h1>易旺</h1></header>",
        "education": "",
        "achievements": "", "certifications": "", "additional_skills": "",
    }
    golden = {
        **shared,
        "work_experience": '<section id="work-experience"><div class="entry"><span class="entry-name">事实公司</span><span class="entry-title">算法工程师</span><span class="entry-year">2023-2025</span><ul><li><strong>核心职责：</strong>负责模型训练与部署</li></ul></div></section>',
        "projects": '<section id="side-projects"><div class="entry"><span class="entry-name">事实项目</span><ul><li><strong>项目背景：</strong>面向业务检索场景建设服务</li><li><strong>核心职责：</strong>负责检索服务的设计与交付</li><li><strong>技术实现：</strong>使用 Python 完成检索服务建设</li><li><strong>验证交付：</strong>按照既定要求完成服务验证</li><li><strong>项目成果：</strong>完成检索服务建设</li></ul></div></section>',
    }
    generic = {
        **shared,
        "work_experience": '<section id="work-experience"><div class="entry"><span class="entry-name">事实公司</span><span class="entry-title">算法工程师</span><span class="entry-year">2023-2025</span><ul><li>深度赋能业务并打造现象级能力</li></ul></div></section>',
        "projects": '<section id="side-projects"><div class="entry"><span class="entry-name">事实项目</span><ul><li>全方位赋能项目并获得市场高度认可</li></ul></div></section>',
    }
    durations, golden_evaluation = timed(lambda: evaluate_resume_candidate(golden, resume), 100)
    generic_evaluation = evaluate_resume_candidate(generic, resume)

    unsafe = dict(golden)
    unsafe["header"] = '<header class="kept"><h1>错误姓名</h1></header>'
    unsafe["work_experience"] = unsafe["work_experience"].replace("事实公司", "错误公司").replace(
        "</ul>", '<li class="fake">效率提升 99%</li></ul>'
    )
    protected = protect_hard_facts_in_place(unsafe, resume)
    protected_html = "\n".join(protected.sections.values())
    checks = ["易旺" in protected_html, "事实公司" in protected_html, "错误姓名" not in protected_html,
              "错误公司" not in protected_html, "99%" not in protected_html]
    generated = generate_candidates(lambda: "candidate", count=3)
    return {
        "golden_score": golden_evaluation.score,
        "generic_score": generic_evaluation.score,
        "golden_score_margin": round(golden_evaluation.score - generic_evaluation.score, 3),
        "project_required_fields_percent": round(
            golden_evaluation.breakdown["project_required_fields"] / 12.0 * 100,
            2,
        ),
        "hard_fact_correction_percent": round(sum(checks) / len(checks) * 100, 2),
        "rich_markup_retention_percent": 100.0 if 'class="kept"' in protected_html else 0.0,
        "successful_candidate_count": float(len(generated)),
        "p95_scorer_latency_ms": round(percentile(durations, .95), 3),
    }


def run_benchmarks() -> dict[str, Any]:
    started = time.perf_counter()
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        result = {
            "context": benchmark_context(),
            "cache": benchmark_cache(root / "cache.sqlite3"),
            "memory": benchmark_memory(root / "memory.sqlite3"),
            "gateway": benchmark_gateway(),
            "skills": benchmark_skills_and_prompts(),
            "resume_quality": benchmark_resume_quality(),
        }
    result["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return result


def check_budgets(report: dict[str, Any], budgets_path: Path) -> list[str]:
    budgets = json.loads(budgets_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for dotted_key, rule in budgets.items():
        value: Any = report
        for part in dotted_key.split("."):
            value = value[part]
        if "min" in rule and value < rule["min"]:
            failures.append(f"{dotted_key}={value} is below minimum {rule['min']}")
        if "max" in rule and value > rule["max"]:
            failures.append(f"{dotted_key}={value} exceeds maximum {rule['max']}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail when a performance budget is violated")
    parser.add_argument("--budgets", type=Path, default=DEFAULT_BUDGETS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_benchmarks()
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    if args.check:
        failures = check_budgets(report, args.budgets)
        if failures:
            print("\nAI Engine regression gate failed:", file=sys.stderr)
            for failure in failures:
                print(f"- {failure}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
