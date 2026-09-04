import json

from backend.api.endpoints import job_tracker
from backend.services import job_followup_service as followup


def test_detect_supported_recruitment_platforms():
    assert followup.detect_platform("https://app.mokahr.com/candidate") == "moka"
    assert followup.detect_platform("https://example.jobs.feishu.cn/candidate") == "feishu"
    assert followup.detect_platform("https://company.zhiye.com/personal") == "zhiye"
    assert followup.detect_platform("https://job.byd.com/portal/pc/#/personalCenter/myApply") == "byd"
    assert followup.detect_platform("https://cmbnt.cmbchina.com/center/history") == "cmb"
    assert followup.detect_platform("https://careers.example.com") == "generic"


def test_extract_status_requires_explicit_status_marker():
    assert followup.extract_status("您的申请正在简历筛选中")[0] == "简历筛选"
    assert followup.extract_status("恭喜，录用通知已经发送")[0] == "Offer"
    assert followup.extract_status("当前进度：简历初筛-进行中") == ("简历筛选", "简历初筛-进行中")
    assert followup.extract_status("AI Agent 开发\nHR初筛\n查看职位") == ("简历筛选", "hr初筛")
    assert followup.extract_status("当前状态：待处理") == ("简历筛选", "待处理")
    assert followup.extract_status("欢迎查看公司招聘岗位") == (None, "")
    assert followup.extract_status("AI应用开发\n申请流程：投递 简历筛选 面试 Offer")[0] == "简历筛选"
    assert followup.extract_status("当前状态：Offer") == ("Offer", "Offer")
    assert followup.extract_status("恭喜，Offer 已发放") == ("Offer", "offer已发放")


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


def test_scheduled_followup_publishes_only_confirmed_status_changes(monkeypatch):
    records = [{
        "id": 1, "company": "示例公司", "role": "算法工程师", "status": "简历筛选",
        "followup_enabled": True, "status_history": [],
    }]
    published = []
    monkeypatch.setattr(job_tracker, "_load_records", lambda: records)
    monkeypatch.setattr(job_tracker, "_save_records", lambda _records: None)
    monkeypatch.setattr(job_tracker, "_publish_status_changes", lambda changed: published.extend(changed))
    monkeypatch.setattr(job_tracker.job_followup_service, "check_application", lambda _record: {
        "status": "技术面", "raw_status": "进入面试", "checked_at": "2026-08-24T12:00:00+08:00",
        "connection_state": "connected",
    })

    result = job_tracker.run_followup_all()

    assert result["checked"] == 1
    assert records[0]["status"] == "技术面"
    assert published[0]["status"] == "技术面"


def test_legacy_job_entry_gets_safe_followup_defaults():
    entry = job_tracker.JobEntry(
        id=1, company="示例公司", role="工程师", base="北京", remark="秋招",
        link="https://example.com", status="简历筛选", icon="", notes="",
    )
    assert entry.followup_enabled is False
    assert entry.followup_ai_enabled is True
    assert entry.followup_state == "not_connected"
    assert entry.status_history == []


def test_rejection_stops_followup_but_still_notifies(monkeypatch):
    events = []
    monkeypatch.setattr(job_tracker, "_safe_notify", lambda *args, **kwargs: events.append(args) or {"sent": 1})
    for status in ("简历挂", "技术面挂", "主管面挂"):
        record = {"id": 1, "status": "简历筛选", "followup_enabled": True}
        assert job_tracker._apply_followup_result(record, {"status": status}, notify=True)
        assert record["followup_enabled"] is False
        assert record["status_history"][-1]["status"] == status
        assert record["last_notification"]["sent"] == 1
    assert len(events) == 3


def test_partial_rejection_does_not_stop_other_applications():
    record = {"id": 1, "status": "简历筛选", "followup_enabled": True}
    job_tracker._apply_followup_result(record, {
        "status": None,
        "application_statuses": [{"role": "岗位甲", "status": "简历挂"}, {"role": "岗位乙", "status": "简历筛选"}],
    })
    assert record["followup_enabled"] is True


def test_existing_rejected_record_is_disabled_and_skipped(monkeypatch, tmp_path):
    path = tmp_path / "records.json"
    path.write_text(json.dumps([{"id": 1, "status": "简历挂", "followup_enabled": True}]), encoding="utf-8")
    monkeypatch.setattr(job_tracker, "DATA_DIR", tmp_path)
    monkeypatch.setattr(job_tracker, "DATA_FILE", path)
    monkeypatch.setattr(followup, "check_application", lambda _: (_ for _ in ()).throw(AssertionError("must not query rejected records")))
    result = job_tracker.run_followup_all()
    assert result["checked"] == 0
    assert json.loads(path.read_text("utf-8"))[0]["followup_enabled"] is False


def test_save_cannot_reenable_rejected_record(monkeypatch, tmp_path):
    path = tmp_path / "records.json"
    monkeypatch.setattr(job_tracker, "DATA_DIR", tmp_path)
    monkeypatch.setattr(job_tracker, "DATA_FILE", path)
    job_tracker._save_records([{"id": 1, "status": "技术面挂", "followup_enabled": True}])
    assert json.loads(path.read_text("utf-8"))[0]["followup_enabled"] is False


def test_auth_notification_dedup_follows_user_schedule(monkeypatch):
    sent = {}
    monkeypatch.setattr(job_tracker, "get_followup_schedule", lambda: {"interval_hours": 8})
    monkeypatch.setattr(job_tracker, "_safe_notify", lambda *args, **kwargs: sent.update(kwargs) or {"sent": 1})
    record = {"id": 7, "company": "示例公司", "role": "AI Agent", "status": "简历筛选"}

    job_tracker._apply_followup_result(record, {
        "result": "verification_required", "connection_state": "verification_required",
        "message": "网站要求完成人机验证", "checked_at": "2026-08-12T08:00:00+00:00",
    }, notify=True)

    assert sent["event_key"] == "auth:7:verification_required"
    assert sent["dedup_seconds"] == 8 * 3600 - 300


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
    assert "--restore-last-session" in captured["args"]
    assert all("webdriver" not in arg.lower() for arg in captured["args"])
    assert followup.complete_login("generic")["status"] == "browser_open"
    process.returncode = 0
    assert followup.complete_login("generic")["status"] == "connected"


def test_plain_sms_code_text_is_not_misclassified_as_human_verification():
    text = "手机号登录 获取验证码"
    assert not any(marker.lower() in text.lower() for marker in followup.VERIFY_MARKERS)
    assert any(marker.lower() in text.lower() for marker in followup.LOGIN_MARKERS)


def test_restored_matching_tab_is_activated():
    class Switcher:
        def __init__(self, driver):
            self.driver = driver

        def window(self, handle):
            self.driver.active = handle

    class Driver:
        window_handles = ["blank", "cmb"]
        active = "blank"

        def __init__(self):
            self.switch_to = Switcher(self)

        @property
        def current_url(self):
            return {"blank": "data:,", "cmb": "https://cmbnt.cmbchina.com/center/history"}[self.active]

    driver = Driver()
    followup._activate_restored_portal_tab(driver, "https://cmbnt.cmbchina.com/center/history")
    assert driver.active == "cmb"


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


def test_bare_offer_requires_an_explicit_current_status_label():
    payload = {
        "matched_application": True, "normalized_status": "Offer", "raw_status": "Offer",
        "confidence": 0.99, "application_match_confidence": 0.99, "status_confidence": 0.99,
    }
    assert followup._validated_llm_result(payload, "AI应用开发\n流程：投递 筛选 面试 Offer", "简历筛选") is None
    assert followup._validated_llm_result(payload, "AI应用开发\n当前状态：Offer", "简历筛选") == {
        "status": "Offer", "raw_status": "Offer", "confidence": 0.99,
    }


def test_same_status_can_be_confirmed_at_lower_risk_threshold():
    context = "蔚来汽车\nAI Agent 开发\n当前状态：简历筛选"
    payload = {
        "matched_application": True, "normalized_status": "简历筛选",
        "raw_status": "简历筛选", "confidence": 0.70,
        "application_match_confidence": 0.70, "status_confidence": 0.92,
    }
    assert followup._validated_llm_result(payload, context, "简历筛选") == {
        "status": "简历筛选", "raw_status": "简历筛选", "confidence": 0.70,
    }
    assert followup._validated_llm_result(payload, context, "技术面") is None


def test_low_confidence_status_change_keeps_candidate_for_review(monkeypatch):
    monkeypatch.setattr(followup, "classify_status_with_llm", lambda context, record: {
        "status": "技术面", "raw_status": "专业交流环节", "confidence": 0.70,
        "matched_application": True, "application_match_confidence": 0.72,
        "status_confidence": 0.93, "reason": "岗位名称为简称",
        "usage": {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
        "cache_hit": False,
    })
    result = followup.classify_application_status(
        "蔚来汽车\nAI Agent 开发\n专业交流环节",
        "蔚来汽车\nAI Agent 开发\n专业交流环节",
        {"company": "蔚来汽车", "role": "Agent 开发", "status": "简历筛选"},
    )
    assert result["status"] is None
    assert result["llm_confidence"] == 0.70
    assert result["llm_candidate_status"] == "技术面"
    assert result["llm_candidate_evidence"] == "专业交流环节"
    assert result["llm_usage"]["total_tokens"] == 100
    assert "更新投递状态" in result["fallback_error"]


def test_evidence_excerpt_masks_contact_information():
    excerpt = followup._evidence_excerpt(
        "候选人 13812345678 test@example.com 当前状态：简历筛选 页面结束",
        "简历筛选",
    )
    assert "13812345678" not in excerpt
    assert "test@example.com" not in excerpt
    assert "简历筛选" in excerpt


def test_three_parallel_applications_are_preserved_without_forcing_one_status(monkeypatch):
    monkeypatch.setattr(followup, "classify_status_with_llm", lambda context, record: {
        "status": "unknown", "raw_status": "", "confidence": 0.88,
        "matched_application": True, "application_match_confidence": 0.90,
        "status_confidence": 0.90, "reason": "三条并行申请状态不同",
        "applications": [
            {"role": "AI Agent 开发", "matched_target": True, "normalized_status": "简历筛选", "raw_status": "筛选中", "confidence": 0.91, "application_match_confidence": 0.92, "status_confidence": 0.93},
            {"role": "AI 视觉开发", "matched_target": True, "normalized_status": "技术面", "raw_status": "专业面试", "confidence": 0.90, "application_match_confidence": 0.91, "status_confidence": 0.94},
            {"role": "算法工程师", "matched_target": True, "normalized_status": "简历筛选", "raw_status": "待处理", "confidence": 0.89, "application_match_confidence": 0.90, "status_confidence": 0.92},
        ],
        "usage": {"input_tokens": 180, "output_tokens": 80, "total_tokens": 260},
        "cache_hit": False,
    })
    page = "AI Agent 开发 筛选中\nAI 视觉开发 专业面试\n算法工程师 待处理"
    result = followup.classify_application_status(page, page, {
        "company": "蔚来汽车", "role": "AI Agent 开发，AI 视觉开发", "status": "简历筛选",
    })
    assert result["status"] is None
    assert result["llm_candidate_status"] == "多岗位"
    assert len(result["application_statuses"]) == 3
    assert result["application_statuses"][1]["status"] == "技术面"
    assert "未覆盖汇总状态" in result["fallback_error"]


def test_submission_receipts_in_application_list_confirm_initial_screening(monkeypatch):
    applications = [
        {"role": role, "matched_target": True, "normalized_status": "简历筛选", "raw_status": "投递简历", "confidence": 0.62, "application_match_confidence": 0.95, "status_confidence": 0.45}
        for role in ("跨端Agent开发工程师", "AI视觉模型开发工程师", "agent研发工程师")
    ]
    monkeypatch.setattr(followup, "classify_status_with_llm", lambda context, record: {
        "status": "简历筛选", "raw_status": "投递简历", "confidence": 0.62,
        "matched_application": True, "application_match_confidence": 0.95,
        "status_confidence": 0.45, "reason": "应聘记录已收到简历",
        "applications": applications,
        "usage": {"input_tokens": 450, "output_tokens": 117, "total_tokens": 567},
        "cache_hit": False,
    })
    page = (
        "应聘记录\n跨端Agent开发工程师 内推投递 投递简历 2026-08-12\n"
        "AI视觉模型开发工程师 内推投递 投递简历 2026-08-12\n"
        "agent研发工程师 内推投递 投递简历 2026-08-12"
    )
    result = followup.classify_application_status(page, page, {
        "company": "蔚来汽车", "role": "跨端Agent开发，AI视觉模型开发，agent研发",
        "status": "简历筛选",
    })
    assert result["status"] == "简历筛选"
    assert result["parser"] == "llm"
    assert all(item["accepted"] for item in result["application_statuses"])
    assert all(item["status_inferred_by_rule"] for item in result["application_statuses"])
    assert all(item["status_confidence"] == 1.0 for item in result["application_statuses"])
    excerpts = result["llm_evidence_excerpt"].split(" | ")
    assert len(excerpts) == len(set(excerpts))


def test_submission_button_outside_application_list_is_not_a_receipt():
    assert followup._is_submission_receipt(
        "职位详情\n欢迎投递\n投递简历", "简历筛选", "投递简历",
    ) is False


def test_terminal_status_overrides_receipt_only_for_matching_application(monkeypatch):
    roles = ("提前批-跨端Agent开发工程师", "提前批-AI视觉模型开发工程师", "提前批-agent研发工程师")
    applications = [
        {"role": role, "matched_target": True, "normalized_status": "简历筛选", "raw_status": "投递简历", "confidence": 0.95, "application_match_confidence": 0.98, "status_confidence": 0.95}
        for role in roles
    ]
    monkeypatch.setattr(followup, "classify_status_with_llm", lambda context, record: {
        "status": "简历筛选", "raw_status": "投递简历", "confidence": 0.95,
        "matched_application": True, "application_match_confidence": 0.98,
        "status_confidence": 0.95, "reason": "投递记录", "applications": applications,
        "usage": {"input_tokens": 300, "output_tokens": 100, "total_tokens": 400},
        "cache_hit": False,
    })
    page = (
        "应聘记录\n提前批-跨端Agent开发工程师 内推投递 投递简历 2026-08-12 流程终止 2026-08-12\n"
        "提前批-AI视觉模型开发工程师 内推投递 投递简历 2026-08-12 流程终止 2026-08-12\n"
        "提前批-agent研发工程师 内推投递 投递简历 2026-08-12"
    )

    result = followup.classify_application_status(page, page, {
        "company": "蔚来汽车", "role": "跨端agent开发，ai视觉模型开发，agent研发",
        "status": "简历筛选",
    })

    assert result["status"] is None
    assert result["parser"] == "llm"
    assert [item["status"] for item in result["application_statuses"]] == ["简历挂", "简历挂", "简历筛选"]
    assert [item["raw_status"] for item in result["application_statuses"]] == ["流程终止", "流程终止", "投递简历"]
    assert all(item["accepted"] for item in result["application_statuses"])


def test_terminal_marker_does_not_leak_across_application_rows():
    roles = ["岗位甲", "岗位乙"]
    page = "岗位甲 投递简历 流程终止 岗位乙 投递简历"
    assert followup._terminal_status_for_application(page, "岗位甲", roles) == ("简历挂", "流程终止")
    assert followup._terminal_status_for_application(page, "岗位乙", roles) is None


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
