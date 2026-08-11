from backend.api.endpoints import job_tracker
from backend.services import job_followup_service as followup


def test_detect_supported_recruitment_platforms():
    assert followup.detect_platform("https://app.mokahr.com/candidate") == "moka"
    assert followup.detect_platform("https://example.jobs.feishu.cn/candidate") == "feishu"
    assert followup.detect_platform("https://company.zhiye.com/personal") == "zhiye"
    assert followup.detect_platform("https://careers.example.com") == "generic"


def test_extract_status_requires_explicit_status_marker():
    assert followup.extract_status("您的申请正在简历筛选中")[0] == "简历筛选"
    assert followup.extract_status("恭喜，录用通知已经发送")[0] == "Offer"
    assert followup.extract_status("当前进度：简历初筛-进行中") == ("简历筛选", "简历初筛-进行中")
    assert followup.extract_status("AI Agent 开发\nHR初筛\n查看职位") == ("简历筛选", "hr初筛")
    assert followup.extract_status("当前状态：待处理") == ("简历筛选", "待处理")
    assert followup.extract_status("欢迎查看公司招聘岗位") == (None, "")


def test_application_context_does_not_use_another_jobs_status():
    page = "甲公司\n算法工程师\n简历筛选中\n乙公司\n产品经理\n已录用"
    context = followup.application_context(page, "甲公司", "算法工程师")
    assert "简历筛选中" in context
    assert "已录用" not in context


def test_followup_result_updates_status_and_appends_timeline():
    record = {"id": 1, "status": "简历筛选", "status_history": []}
    job_tracker._apply_followup_result(record, {
        "status": "技术面", "raw_status": "进入面试", "checked_at": "2026-08-11T00:00:00+00:00",
        "evidence_url": "https://example.com/application", "connection_state": "connected",
    })
    assert record["status"] == "技术面"
    assert record["followup_state"] == "connected"
    assert record["last_raw_status"] == "进入面试"
    assert record["status_history"][0]["status"] == "技术面"


def test_legacy_job_entry_gets_safe_followup_defaults():
    entry = job_tracker.JobEntry(
        id=1, company="示例公司", role="工程师", base="北京", remark="秋招",
        link="https://example.com", status="简历筛选", icon="", notes="",
    )
    assert entry.followup_enabled is False
    assert entry.followup_ai_enabled is True
    assert entry.followup_state == "not_connected"
    assert entry.status_history == []


def test_login_uses_normal_chrome_process_instead_of_webdriver(monkeypatch, tmp_path):
    class FakeProcess:
        returncode = None

        def poll(self):
            return self.returncode

    captured = {}
    process = FakeProcess()
    monkeypatch.setattr(followup, "_find_chrome_binary", lambda: "chrome.exe")
    monkeypatch.setattr(followup, "_profile_dir", lambda _platform: tmp_path)
    monkeypatch.setattr(followup.subprocess, "Popen", lambda args: captured.setdefault("args", args) and process)
    followup._LOGIN_BROWSERS.clear()

    opened = followup.open_login_browser("generic", "https://careers.example.com/personal")
    assert opened["status"] == "browser_open"
    assert "--user-data-dir=" + str(tmp_path) in captured["args"]
    assert all("webdriver" not in arg.lower() for arg in captured["args"])
    assert followup.complete_login("generic")["status"] == "browser_open"
    process.returncode = 0
    assert followup.complete_login("generic")["status"] == "connected"


def test_unknown_local_status_uses_llm_fallback(monkeypatch):
    monkeypatch.setattr(followup, "classify_status_with_llm", lambda context, record: {
        "status": "技术面", "raw_status": "专业交流环节", "confidence": 0.93,
        "usage": {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100}, "cache_hit": False,
    })
    result = followup.classify_application_status(
        "示例公司\n算法工程师\n专业交流环节", "示例公司\n算法工程师\n专业交流环节",
        {"company": "示例公司", "role": "算法工程师", "followup_ai_enabled": True},
    )
    assert result["status"] == "技术面"
    assert result["parser"] == "llm"
    assert result["llm_usage"]["total_tokens"] == 100


def test_llm_result_must_quote_page_evidence():
    context = "示例公司\n算法工程师\n专业交流环节"
    valid = followup._validated_llm_result({
        "matched_application": True, "normalized_status": "技术面",
        "raw_status": "专业交流环节", "confidence": 0.91,
    }, context)
    hallucinated = followup._validated_llm_result({
        "matched_application": True, "normalized_status": "Offer",
        "raw_status": "已录用", "confidence": 0.99,
    }, context)
    assert valid == {"status": "技术面", "raw_status": "专业交流环节", "confidence": 0.91}
    assert hallucinated is None


def test_ai_fallback_can_be_disabled(monkeypatch):
    monkeypatch.setattr(followup, "classify_status_with_llm", lambda *_: (_ for _ in ()).throw(AssertionError()))
    result = followup.classify_application_status("未知状态", "未知状态", {"followup_ai_enabled": False})
    assert result["parser"] == "none"
    assert result["fallback_error"] == "AI 兜底未启用"


def test_llm_context_keeps_status_farther_from_target_row():
    page = "页面导航\n示例公司\n算法工程师\n" + "操作按钮\n" * 8 + "专业交流环节\n页脚"
    local_context = followup.application_context(page, "示例公司", "算法工程师")
    assert "专业交流环节" not in local_context
    assert "专业交流环节" in followup._llm_page_context(page, local_context, "示例公司", "算法工程师")


def test_multi_preference_page_is_delegated_to_llm(monkeypatch):
    page = (
        "应聘状态\n校招项目 志愿一 志愿二 投递时间 操作\n技术专场\n"
        "服务端研发工程师\n服务端研发工程师\n当前状态：待处理\n"
        "当前应聘职位：服务端研发工程师\n拼多多集团 - PDD 校园招聘"
    )
    context = followup.application_context(page, "拼多多", "AI Agent 开发")
    monkeypatch.setattr(followup, "classify_status_with_llm", lambda llm_context, record: {
        "status": "简历筛选", "raw_status": "待处理", "confidence": 0.96,
        "usage": {"input_tokens": 120, "output_tokens": 25, "total_tokens": 145}, "cache_hit": False,
    })
    result = followup.classify_application_status(page, context, {
        "company": "拼多多", "role": "AI Agent 开发", "followup_ai_enabled": True,
    })
    assert result["parser"] == "llm"
    assert result["status"] == "简历筛选"
    assert result["raw_status"] == "待处理"
