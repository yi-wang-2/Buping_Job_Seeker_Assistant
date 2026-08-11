"""Local notification delivery for job follow-up events."""

from __future__ import annotations

import hashlib
import json
import os
import re
import smtplib
import sqlite3
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib import parse, request

from backend.services.config_service import load_secrets, save_secrets


ROOT = Path(__file__).resolve().parents[2]
LOG_DB = ROOT / "data_folder" / "job_tracker" / "notifications.sqlite3"
SECRET_FIELDS = {"notification_smtp_password", "notification_serverchan_sendkey"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_schema() -> None:
    LOG_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(LOG_DB, timeout=5) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS notification_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_key TEXT NOT NULL,
                channel TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_notification_event ON notification_deliveries(event_key, channel, created_at)")


def get_settings(*, include_secrets: bool = False) -> dict[str, Any]:
    secrets = load_secrets()
    result = {
        "email_enabled": bool(secrets.get("notification_email_enabled", False)),
        "smtp_host": str(secrets.get("notification_smtp_host", "")),
        "smtp_port": int(secrets.get("notification_smtp_port", 465) or 465),
        "smtp_username": str(secrets.get("notification_smtp_username", "")),
        "smtp_from": str(secrets.get("notification_smtp_from", "")),
        "smtp_to": str(secrets.get("notification_smtp_to", "")),
        "smtp_security": str(secrets.get("notification_smtp_security", "ssl")),
        "wechat_enabled": bool(secrets.get("notification_wechat_enabled", False)),
        "smtp_password_configured": bool(secrets.get("notification_smtp_password", "")),
        "serverchan_sendkey_configured": bool(secrets.get("notification_serverchan_sendkey", "")),
    }
    if include_secrets:
        result["smtp_password"] = str(secrets.get("notification_smtp_password", ""))
        result["serverchan_sendkey"] = str(secrets.get("notification_serverchan_sendkey", ""))
    return result


def save_settings(values: dict[str, Any]) -> dict[str, Any]:
    current = get_settings(include_secrets=True)
    security = str(values.get("smtp_security", "ssl"))
    if security not in {"ssl", "starttls", "none"}:
        raise ValueError("SMTP 加密方式无效")
    smtp_port = int(values.get("smtp_port", 465))
    if not 1 <= smtp_port <= 65535:
        raise ValueError("SMTP 端口必须在 1 到 65535 之间")
    updates = {
        "notification_email_enabled": bool(values.get("email_enabled", False)),
        "notification_smtp_host": str(values.get("smtp_host", "")).strip(),
        "notification_smtp_port": smtp_port,
        "notification_smtp_username": str(values.get("smtp_username", "")).strip(),
        "notification_smtp_from": str(values.get("smtp_from", "")).strip(),
        "notification_smtp_to": str(values.get("smtp_to", "")).strip(),
        "notification_smtp_security": security,
        "notification_wechat_enabled": bool(values.get("wechat_enabled", False)),
    }
    password = str(values.get("smtp_password", ""))
    sendkey = str(values.get("serverchan_sendkey", ""))
    updates["notification_smtp_password"] = password if password else current.get("smtp_password", "")
    updates["notification_serverchan_sendkey"] = sendkey if sendkey else current.get("serverchan_sendkey", "")
    if updates["notification_email_enabled"]:
        if not updates["notification_smtp_host"] or not updates["notification_smtp_to"] or not (
            updates["notification_smtp_from"] or updates["notification_smtp_username"]
        ):
            raise ValueError("启用邮件通知时必须填写 SMTP 主机、发件账号和收件邮箱")
    if updates["notification_wechat_enabled"] and not updates["notification_serverchan_sendkey"]:
        raise ValueError("启用个人微信通知时必须填写 Server酱 SendKey")
    save_secrets(updates)
    return get_settings()


def _event_hash(event_key: str) -> str:
    return hashlib.sha256(event_key.encode("utf-8")).hexdigest()


def _delivered_recently(event_key: str, channel: str, seconds: int) -> bool:
    _ensure_schema()
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    with sqlite3.connect(LOG_DB, timeout=5) as db:
        row = db.execute(
            "SELECT 1 FROM notification_deliveries WHERE event_key=? AND channel=? AND status='success' AND created_at>=? LIMIT 1",
            (_event_hash(event_key), channel, cutoff),
        ).fetchone()
    return row is not None


def _record(event_key: str, channel: str, status: str, error: str = "") -> None:
    _ensure_schema()
    with sqlite3.connect(LOG_DB, timeout=5) as db:
        db.execute(
            "INSERT INTO notification_deliveries(event_key,channel,status,error,created_at) VALUES(?,?,?,?,?)",
            (_event_hash(event_key), channel, status, error[:500], _now()),
        )


def _send_email(config: dict[str, Any], title: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = title
    message["From"] = config["smtp_from"] or config["smtp_username"]
    message["To"] = config["smtp_to"]
    message.set_content(body)
    host, port = config["smtp_host"], int(config["smtp_port"])
    if config["smtp_security"] == "ssl":
        with smtplib.SMTP_SSL(host, port, timeout=12, context=ssl.create_default_context()) as client:
            if config["smtp_username"]:
                client.login(config["smtp_username"], config["smtp_password"])
            client.send_message(message)
        return
    with smtplib.SMTP(host, port, timeout=12) as client:
        if config["smtp_security"] == "starttls":
            client.starttls(context=ssl.create_default_context())
        if config["smtp_username"]:
            client.login(config["smtp_username"], config["smtp_password"])
        client.send_message(message)


def _send_wechat(config: dict[str, Any], title: str, body: str) -> None:
    endpoint = _serverchan_endpoint(config["serverchan_sendkey"])
    payload = parse.urlencode({"title": title[:32], "desp": body}).encode("utf-8")
    req = request.Request(endpoint, data=payload, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with request.urlopen(req, timeout=12) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        # Do not expose a URL containing the SendKey in logs or API responses.
        raise RuntimeError(f"Server酱请求失败（{type(exc).__name__}）") from exc
    if int(result.get("code", -1)) != 0:
        raise RuntimeError(str(result.get("message") or result.get("data") or "Server酱推送失败"))


def _serverchan_endpoint(raw_sendkey: str) -> str:
    sendkey = str(raw_sendkey).strip()
    encoded = parse.quote(sendkey, safe="")
    sc3 = re.match(r"^sctp(\d+)t", sendkey, re.IGNORECASE)
    if sc3:
        return f"https://{sc3.group(1)}.push.ft07.com/send/{encoded}.send"
    return f"https://sctapi.ftqq.com/{encoded}.send"


def send_notification(
    title: str, body: str, *, event_key: str, dedup_seconds: int = 86400,
) -> dict[str, Any]:
    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("BUPING_ALLOW_TEST_NOTIFICATIONS") != "1":
        return {"sent": 0, "results": [{"channel": "test", "status": "suppressed"}]}
    config = get_settings(include_secrets=True)
    channels = []
    if config["email_enabled"]:
        channels.append(("email", _send_email))
    if config["wechat_enabled"]:
        channels.append(("wechat", _send_wechat))
    results = []
    for channel, sender in channels:
        if dedup_seconds and _delivered_recently(event_key, channel, dedup_seconds):
            results.append({"channel": channel, "status": "deduplicated"})
            continue
        try:
            sender(config, title, body)
            _record(event_key, channel, "success")
            results.append({"channel": channel, "status": "success"})
        except Exception as exc:
            _record(event_key, channel, "error", str(exc))
            results.append({"channel": channel, "status": "error", "error": str(exc)})
    return {"sent": sum(item["status"] == "success" for item in results), "results": results}


def send_test_notification() -> dict[str, Any]:
    return send_notification(
        "不平：通知测试成功", "这是一条求职状态通知测试。收到此消息说明通知渠道配置正常。",
        event_key=f"test:{_now()}", dedup_seconds=0,
    )
