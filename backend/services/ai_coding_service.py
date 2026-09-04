"""Deterministic AI-coding practice sessions and assessment."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SESSION_DIR = ROOT / "data_folder" / "ai_coding" / "sessions"

TASKS: dict[str, dict[str, Any]] = {
    "python-normalize-tags": {
        "id": "python-normalize-tags",
        "title": "清洗职位技能标签",
        "language": "Python",
        "difficulty": "入门",
        "duration_minutes": 35,
        "summary": "修复并完善一个用于清洗职位技能标签的函数。",
        "description": (
            "实现 normalize_tags(raw_tags)。输入可能包含字符串、None 和其他类型；"
            "忽略非字符串与空白项，去除首尾空格，转为小写，按首次出现顺序去重。"
        ),
        "requirements": [
            "函数必须返回 list[str]",
            "比较时不区分大小写",
            "保留第一次出现的位置",
            "不能修改输入列表",
        ],
        "starter_code": (
            "def normalize_tags(raw_tags):\n"
            "    # TODO: implement\n"
            "    return []\n"
        ),
        "examples": [
            {"input": "[' Python ', 'FASTAPI', 'python', '', None]", "output": "['python', 'fastapi']"},
        ],
        "public_tests": [
            [[" Python ", "FASTAPI", "python", "", None], ["python", "fastapi"]],
            [[], []],
        ],
        "hidden_tests": [
            [["Go", 42, " go ", "Rust", "RUST "], ["go", "rust"]],
            [["  React  ", "Vue", "react", " vue ", "Svelte"], ["react", "vue", "svelte"]],
            [[None, True, "   ", "SQL"], ["sql"]],
        ],
    }
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session_path(session_id: str) -> Path:
    if not session_id or any(char not in "0123456789abcdef-" for char in session_id.lower()):
        raise ValueError("Invalid session id")
    return SESSION_DIR / f"{session_id}.json"


def _save_session(session: dict[str, Any]) -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    _session_path(session["id"]).write_text(
        json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_session(session_id: str) -> dict[str, Any]:
    path = _session_path(session_id)
    if not path.is_file():
        raise ValueError("训练会话不存在")
    return json.loads(path.read_text(encoding="utf-8"))


def list_tasks() -> list[dict[str, Any]]:
    fields = ("id", "title", "language", "difficulty", "duration_minutes", "summary")
    return [{field: task[field] for field in fields} for task in TASKS.values()]


def start_session(task_id: str) -> dict[str, Any]:
    task = TASKS.get(task_id)
    if task is None:
        raise ValueError("练习题不存在")
    session = {
        "id": str(uuid.uuid4()),
        "task_id": task_id,
        "status": "in_progress",
        "started_at": _now(),
        "submitted_at": None,
    }
    _save_session(session)
    public_task = {key: value for key, value in task.items() if key not in {"public_tests", "hidden_tests"}}
    return {"session": session, "task": public_task}


_RUNNER = r'''
import ast, json, sys
payload = json.loads(sys.stdin.read())
tree = ast.parse(payload["code"])
blocked = (ast.Import, ast.ImportFrom, ast.With, ast.AsyncWith, ast.ClassDef, ast.Global,
           ast.Nonlocal, ast.Lambda, ast.Try, ast.Raise)
if any(isinstance(node, blocked) for node in ast.walk(tree)):
    raise ValueError("代码包含练习环境不允许的语法")
allowed = {"len": len, "str": str, "list": list, "set": set, "dict": dict,
           "enumerate": enumerate, "range": range, "isinstance": isinstance,
           "sorted": sorted, "zip": zip, "bool": bool, "int": int}
scope = {"__builtins__": allowed}
exec(compile(tree, "<submission>", "exec"), scope, scope)
fn = scope.get("normalize_tags")
if not callable(fn):
    raise ValueError("请定义 normalize_tags(raw_tags) 函数")
results = []
for args, expected in payload["tests"]:
    before = json.dumps(args, ensure_ascii=False, sort_keys=True)
    actual = fn(args)
    results.append({"passed": actual == expected and json.dumps(args, ensure_ascii=False, sort_keys=True) == before,
                    "actual": actual, "expected": expected})
print(json.dumps(results, ensure_ascii=False))
'''


def _run_tests(code: str, tests: list[list[Any]]) -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", _RUNNER],
            input=json.dumps({"code": code, "tests": tests}, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            cwd=str(ROOT),
        )
    except subprocess.TimeoutExpired:
        return [{"passed": False, "error": "执行超时（3 秒）"} for _ in tests]
    if result.returncode != 0:
        message = (result.stderr or "代码执行失败").strip().splitlines()[-1]
        return [{"passed": False, "error": message} for _ in tests]
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return [{"passed": False, "error": "程序产生了非预期输出"} for _ in tests]


def submit_session(
    session_id: str,
    code: str,
    approach: str = "",
    test_strategy: str = "",
    ai_reflection: str = "",
) -> dict[str, Any]:
    session = _load_session(session_id)
    if session["status"] == "completed":
        raise ValueError("该训练已经提交")
    task = TASKS[session["task_id"]]
    all_tests = task["public_tests"] + task["hidden_tests"]
    results = _run_tests(code, all_tests)
    passed = sum(bool(item.get("passed")) for item in results)
    correctness = round(60 * passed / len(all_tests))
    explanation_score = min(15, round(len(approach.strip()) * 0.6))
    testing_score = min(15, round(len(test_strategy.strip()) * 0.6))
    reflection_score = min(10, round(len(ai_reflection.strip()) * 0.45))
    total = correctness + explanation_score + testing_score + reflection_score
    dimensions = {
        "correctness": correctness,
        "problem_solving": explanation_score,
        "verification": testing_score,
        "ai_collaboration": reflection_score,
    }
    feedback: list[str] = []
    if passed < len(all_tests):
        feedback.append("先根据失败用例检查类型过滤、大小写去重和输入不可变约束。")
    if explanation_score < 10:
        feedback.append("补充说明数据流、核心不变量以及为什么选择该实现。")
    if testing_score < 10:
        feedback.append("列出正常、空输入、重复值、混合类型和输入不可变测试。")
    if reflection_score < 7:
        feedback.append("记录你如何使用 AI、采纳了什么，以及如何验证 AI 的建议。")
    if not feedback:
        feedback.append("完成度很好；下一步可练习带有多文件调用链的 Bug 修复任务。")
    report = {
        "score": total,
        "passed_tests": passed,
        "total_tests": len(all_tests),
        "dimensions": dimensions,
        "feedback": feedback,
        "public_results": results[: len(task["public_tests"])],
    }
    session.update({
        "status": "completed",
        "submitted_at": _now(),
        "submission": {"code": code, "approach": approach, "test_strategy": test_strategy, "ai_reflection": ai_reflection},
        "report": report,
    })
    _save_session(session)
    return {"session": session, "report": report}


def list_sessions() -> list[dict[str, Any]]:
    if not SESSION_DIR.exists():
        return []
    sessions = []
    for path in SESSION_DIR.glob("*.json"):
        try:
            session = json.loads(path.read_text(encoding="utf-8"))
            sessions.append({
                "id": session["id"],
                "task_id": session["task_id"],
                "task_title": TASKS.get(session["task_id"], {}).get("title", session["task_id"]),
                "status": session["status"],
                "started_at": session["started_at"],
                "score": session.get("report", {}).get("score"),
            })
        except (OSError, ValueError, KeyError):
            continue
    return sorted(sessions, key=lambda item: item["started_at"], reverse=True)
