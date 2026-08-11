from backend.api.endpoints import job_tracker
from backend.services import notification_service as notifications


def test_notification_secrets_are_not_returned(monkeypatch):
    monkeypatch.setattr(notifications, "load_secrets", lambda: {
        "notification_email_enabled": True,
        "notification_smtp_password": "email-secret",
        "notification_serverchan_sendkey": "wechat-secret",
    })
    settings = notifications.get_settings()
    assert settings["smtp_password_configured"] is True
    assert settings["serverchan_sendkey_configured"] is True
    assert "smtp_password" not in settings
    assert "serverchan_sendkey" not in settings


def test_duplicate_event_is_only_sent_once(monkeypatch, tmp_path):
    monkeypatch.setenv("BUPING_ALLOW_TEST_NOTIFICATIONS", "1")
    monkeypatch.setattr(notifications, "LOG_DB", tmp_path / "notifications.sqlite3")
    monkeypatch.setattr(notifications, "get_settings", lambda **_: {
        "email_enabled": True, "wechat_enabled": False,
    })
    sent = []
    monkeypatch.setattr(notifications, "_send_email", lambda config, title, body: sent.append(title))
    first = notifications.send_notification("状态更新", "正文", event_key="same-event")
    second = notifications.send_notification("状态更新", "正文", event_key="same-event")
    assert first["sent"] == 1
    assert second["results"][0]["status"] == "deduplicated"
    assert sent == ["状态更新"]


def test_status_change_and_login_expiry_trigger_notifications(monkeypatch):
    events = []
    monkeypatch.setattr(job_tracker.notification_service, "send_notification", lambda title, body, **kwargs: events.append((title, body, kwargs)) or {"sent": 2, "results": []})
    record = {"id": 7, "company": "示例公司", "role": "算法工程师", "status": "简历筛选", "status_history": []}
    job_tracker._apply_followup_result(record, {
        "result": "changed", "status": "技术面", "raw_status": "专业面试",
        "checked_at": "2026-08-11T00:00:00+00:00", "connection_state": "connected",
    }, notify=True)
    job_tracker._apply_followup_result(record, {
        "result": "login_required", "checked_at": "2026-08-12T00:00:00+00:00",
        "connection_state": "login_required", "message": "登录失效",
    }, notify=True)
    assert len(events) == 2
    assert "原状态：简历筛选" in events[0][1]
    assert "登录已失效" in events[1][1]


def test_notification_failure_does_not_block_status_update(monkeypatch):
    monkeypatch.setattr(job_tracker.notification_service, "send_notification", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    record = {"id": 8, "company": "示例公司", "role": "工程师", "status": "简历筛选", "status_history": []}
    job_tracker._apply_followup_result(record, {
        "result": "changed", "status": "笔试", "raw_status": "在线测评",
        "checked_at": "2026-08-11T00:00:00+00:00", "connection_state": "connected",
    }, notify=True)
    assert record["status"] == "笔试"
    assert record["last_notification"]["results"][0]["status"] == "error"


def test_plain_status_application_never_notifies(monkeypatch):
    monkeypatch.setattr(job_tracker.notification_service, "send_notification", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not send")))
    record = {"id": 9, "status": "简历筛选", "status_history": []}
    job_tracker._apply_followup_result(record, {
        "result": "changed", "status": "技术面", "raw_status": "测试数据",
        "checked_at": "2026-08-11T00:00:00+00:00", "connection_state": "connected",
    })
    assert record["status"] == "技术面"
    assert "last_notification" not in record


def test_serverchan_endpoint_supports_turbo_and_sc3_keys():
    assert notifications._serverchan_endpoint("SCT123") == "https://sctapi.ftqq.com/SCT123.send"
    assert notifications._serverchan_endpoint("sctp456tSecret") == "https://456.push.ft07.com/send/sctp456tSecret.send"
