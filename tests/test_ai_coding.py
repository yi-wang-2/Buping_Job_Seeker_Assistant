from pathlib import Path

import pytest

from backend.services import ai_coding_service


@pytest.fixture()
def isolated_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ai_coding_service, "SESSION_DIR", tmp_path / "sessions")


def test_task_catalog_does_not_expose_hidden_tests():
    tasks = ai_coding_service.list_tasks()
    assert tasks
    assert "hidden_tests" not in tasks[0]


def test_complete_practice_session(isolated_sessions):
    started = ai_coding_service.start_session("python-normalize-tags")
    assert "hidden_tests" not in started["task"]
    result = ai_coding_service.submit_session(
        started["session"]["id"],
        code=(
            "def normalize_tags(raw_tags):\n"
            "    result = []\n"
            "    for item in raw_tags:\n"
            "        if isinstance(item, str):\n"
            "            value = item.strip().lower()\n"
            "            if value and value not in result:\n"
            "                result.append(value)\n"
            "    return result\n"
        ),
        approach="逐项过滤非字符串，标准化大小写后按首次出现顺序去重，并保持输入不变。",
        test_strategy="覆盖空输入、重复大小写、空白、混合类型以及输入列表不被修改。",
        ai_reflection="让 AI 提供边界条件清单，但逐项通过测试验证，没有直接接受生成代码。",
    )
    assert result["report"]["passed_tests"] == result["report"]["total_tests"]
    assert result["report"]["score"] >= 85
    assert ai_coding_service.list_sessions()[0]["status"] == "completed"


def test_rejects_unsafe_submission(isolated_sessions):
    started = ai_coding_service.start_session("python-normalize-tags")
    result = ai_coding_service.submit_session(
        started["session"]["id"],
        code="import os\ndef normalize_tags(raw_tags):\n    return []",
    )
    assert result["report"]["passed_tests"] == 0
    assert result["report"]["public_results"][0]["passed"] is False
