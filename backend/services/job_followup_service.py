"""Local browser-session based application status follow-up.

The service never stores passwords or bypasses verification. A visible browser
is used for user-assisted login; scheduled checks reuse Chrome's own encrypted
profile data and stop when verification is required.
"""

from __future__ import annotations

import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.utils.chrome_utils import _find_chrome_binary, init_browser


ROOT = Path(__file__).resolve().parents[2]
PROFILE_ROOT = ROOT / "data_folder" / "browser_profiles" / "job_followup"
_BROWSER_LOCK = threading.Lock()
_LOGIN_BROWSERS: dict[str, Any] = {}

PLATFORM_HOSTS = {
    "moka": ("mokahr.com",),
    "feishu": ("jobs.feishu.cn",),
    "zhiye": ("zhiye.com",),
    "byd": ("job.byd.com",),
    "cmb": ("cmbnt.cmbchina.com",),
    "generic": (),
}

LOGIN_MARKERS = ("请登录", "立即登录", "登录后查看", "手机号登录", "扫码登录", "账号登录", "账号密码", "sign in", "log in")
VERIFY_MARKERS = ("人机验证", "安全验证", "滑动验证", "图形验证", "captcha", "verify you are human")
STATUS_RULES = (
    ("Offer", ("已录用", "录用通知", "已发放offer", "已发送offer", "offer已发放", "offer已发送", "收到offer")),
    ("三面", ("三面", "第三轮面试", "终面", "终试", "hr面试", "hr 面试", "人力面试")),
    ("二面", ("二面", "第二轮面试", "复试", "主管面试", "业务面试")),
    ("一面", ("一面", "第一轮面试", "初试", "技术面试", "专业面试", "面试中", "进入面试")),
    ("笔试", ("笔试中", "待笔试", "在线测评", "测评中")),
    ("简历挂", ("不合适", "未通过", "流程终止", "已淘汰", "很遗憾")),
    ("简历筛选", ("hr初筛", "初筛", "筛选中", "简历筛选", "处理中", "待处理", "已投递", "投递成功")),
)
ALLOWED_STATUSES = {"简历筛选", "笔试", "一面", "二面", "三面", "Offer", "泡池子", "简历挂"}
STATUS_CHANGE_CONFIDENCE = 0.85
UNCHANGED_CONFIRMATION_CONFIDENCE = 0.65
SUBMISSION_RECEIPT_MARKERS = ("投递简历", "内推投递", "投递成功", "已投递")
APPLICATION_RECORD_MARKERS = ("应聘记录", "投递记录", "申请记录")
TERMINAL_REJECTION_MARKERS = ("流程终止", "已淘汰", "未通过", "不合适", "很遗憾")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def detect_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for platform, hosts in PLATFORM_HOSTS.items():
        if any(host == suffix or host.endswith(f".{suffix}") for suffix in hosts):
            return platform
    return "generic"


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("请输入有效的投递中心 http(s) 链接")


def _profile_dir(platform: str) -> Path:
    safe_platform = platform if platform in PLATFORM_HOSTS else "generic"
    path = PROFILE_ROOT / safe_platform
    path.mkdir(parents=True, exist_ok=True)
    return path


def open_login_browser(platform: str, portal_url: str) -> dict[str, Any]:
    _validate_url(portal_url)
    platform = platform if platform in PLATFORM_HOSTS else detect_platform(portal_url)
    with _BROWSER_LOCK:
        previous = _LOGIN_BROWSERS.get(platform)
        if previous and previous.get("process") and previous["process"].poll() is None:
            return {"status": "browser_open", "platform": platform, "message": "登录窗口已经打开，请完成登录后关闭该 Chrome 窗口"}
        chrome_binary = _find_chrome_binary()
        if not chrome_binary:
            raise RuntimeError("未找到 Google Chrome")
        process = subprocess.Popen([
            chrome_binary,
            f"--user-data-dir={_profile_dir(platform)}",
            "--profile-directory=Default",
            "--restore-last-session",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            portal_url,
        ])
        _LOGIN_BROWSERS[platform] = {"process": process, "portal_url": portal_url}
    return {"status": "browser_open", "platform": platform, "message": "请在普通 Chrome 中完成登录和验证，完成后关闭该窗口，再点击“我已完成登录”"}


def complete_login(platform: str) -> dict[str, Any]:
    with _BROWSER_LOCK:
        session = _LOGIN_BROWSERS.get(platform)
        if not session:
            return {"status": "not_open", "platform": platform, "message": "未找到等待确认的登录窗口"}
        process = session.get("process")
        if process and process.poll() is None:
            return {"status": "browser_open", "platform": platform, "message": "请先关闭刚才打开的普通 Chrome 窗口，再确认登录"}
        _LOGIN_BROWSERS.pop(platform, None)
        return {"status": "connected", "platform": platform, "message": "Chrome 登录会话已保存，可点击“立即检查”验证"}


def _activate_restored_portal_tab(driver: Any, portal_url: str) -> None:
    """Prefer the restored site tab so tab-scoped sessionStorage remains usable."""
    target_host = (urlparse(portal_url).hostname or "").lower()
    if not target_host:
        return
    for handle in driver.window_handles:
        try:
            driver.switch_to.window(handle)
            current_host = (urlparse(driver.current_url).hostname or "").lower()
            if current_host == target_host:
                return
        except Exception:
            continue


def extract_status(page_text: str) -> tuple[str | None, str]:
    normalized = re.sub(r"\s+", " ", page_text).lower()
    normalized_compact = re.sub(r"\s+", "", page_text).lower()
    progress = re.search(r"(?:当前进度|当前状态|申请状态|流程状态|应聘状态)\s*[:：]\s*([^\n]{1,60})", page_text, re.IGNORECASE)
    if progress:
        raw = progress.group(1).strip()
        raw_lower = raw.lower()
        progress_rules = (
            ("Offer", ("offer", "录用")),
            ("简历挂", ("淘汰", "未通过", "不合适", "终止")),
            ("三面", ("三面", "第三轮", "终面", "终试", "hr面", "hr 面", "人力面")),
            ("二面", ("二面", "第二轮", "复试", "主管面", "业务面")),
            ("一面", ("一面", "第一轮", "初试", "技术面", "专业面", "面试")),
            ("笔试", ("笔试", "测评")),
            ("简历筛选", ("初筛", "筛选", "已投递", "处理中", "待处理")),
        )
        for status, markers in progress_rules:
            if any(marker.lower() in raw_lower for marker in markers):
                return status, raw
    for status, markers in STATUS_RULES:
        searchable = normalized_compact if status == "Offer" else normalized
        matched = next((marker for marker in markers if marker.lower() in searchable), None)
        if matched:
            return status, matched
    return None, ""


def application_context(page_text: str, company: str, role: str) -> str:
    """Limit status detection to text near the matching application row."""
    lines = [line.strip() for line in page_text.splitlines() if line.strip()]
    anchors = [value.strip().lower() for value in (company, role)
               if len(value.strip()) >= 3 and value.strip() != "招聘岗位"]
    matched_indexes = [index for index, line in enumerate(lines)
                       if any(anchor in line.lower() or line.lower() in anchor for anchor in anchors)]
    if not matched_indexes:
        return ""
    selected: list[str] = []
    for index in matched_indexes:
        selected.extend(lines[max(0, index - 2):index + 3])
    return "\n".join(dict.fromkeys(selected))


def _llm_page_context(
    page_text: str, matched_context: str, company: str = "", role: str = "", limit: int = 8000,
) -> str:
    """Prefer the matched row, but still support unfamiliar page layouts."""
    excerpts: list[str] = []
    lowered = page_text.lower()
    for anchor in (company.strip(), role.strip()):
        if len(anchor) < 3:
            continue
        start = 0
        for _ in range(3):
            index = lowered.find(anchor.lower(), start)
            if index < 0:
                break
            excerpts.append(page_text[max(0, index - 1200):index + len(anchor) + 1800])
            start = index + len(anchor)
    source = "\n...[目标片段分隔]...\n".join(dict.fromkeys(
        [value for value in (matched_context.strip(), *excerpts) if value]
    )) or page_text.strip()
    if len(source) <= limit:
        return source
    # Preserve both ends because SPA application lists often put status panels last.
    half = limit // 2
    return f"{source[:half]}\n...[页面中段已截断]...\n{source[-half:]}"


def _confidence(payload: dict[str, Any], field: str) -> float:
    value = payload.get(field)
    if value is None:
        value = payload.get("confidence")
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _is_submission_receipt(context: str, status: str, evidence: str) -> bool:
    """Treat a receipt marker inside an application list as initial screening.

    The application-list guard prevents a generic job-detail CTA such as
    "投递简历" from being mistaken for an already submitted application.
    """
    return (
        status == "简历筛选"
        and any(marker in context for marker in APPLICATION_RECORD_MARKERS)
        and any(marker in evidence or marker in context for marker in SUBMISSION_RECEIPT_MARKERS)
    )


def _terminal_status_for_application(
    context: str, role: str, application_roles: list[str],
) -> tuple[str, str] | None:
    """Find a terminal marker only inside the matching application's row."""
    role = role.strip()
    roles = [value.strip() for value in application_roles if value.strip()]
    if not context or not role or not roles:
        return None
    lowered = context.lower()
    for match in re.finditer(re.escape(role.lower()), lowered):
        content_start = match.end()
        boundaries = [
            next_match.start()
            for candidate in roles
            for next_match in [re.search(re.escape(candidate.lower()), lowered[content_start:])]
            if next_match is not None
        ]
        content_end = content_start + min(boundaries) if boundaries else min(len(context), content_start + 1600)
        segment = context[content_start:content_end]
        for marker in TERMINAL_REJECTION_MARKERS:
            if marker.lower() in segment.lower():
                return "简历挂", marker
    return None


def _effective_status_confidence(payload: dict[str, Any], context: str) -> float:
    status = str(payload.get("normalized_status") or "").strip()
    evidence = str(payload.get("raw_status") or "").strip()
    if _is_submission_receipt(context, status, evidence):
        return 1.0
    return _confidence(payload, "status_confidence")


def _has_explicit_offer_evidence(context: str, status: str, evidence: str) -> bool:
    if status != "Offer":
        return True
    evidence_lower = re.sub(r"\s+", "", evidence).lower()
    strong_markers = ("已录用", "录用通知", "已发放offer", "已发送offer", "offer已发放", "offer已发送", "收到offer")
    if any(marker in evidence_lower for marker in strong_markers):
        return True
    # A bare `Offer` is acceptable only when the page explicitly labels it as
    # the current status. Navigation items and process-step names are not state.
    return bool(re.search(
        r"(?:当前进度|当前状态|申请状态|流程状态|应聘状态)\s*[:：]\s*offer\b",
        context,
        re.IGNORECASE,
    ))


def _validated_llm_result(
    payload: dict[str, Any], context: str, current_status: str = "",
) -> dict[str, Any] | None:
    status = str(payload.get("normalized_status") or "").strip()
    evidence = str(payload.get("raw_status") or "").strip()
    confidence = _confidence(payload, "confidence")
    match_confidence = _confidence(payload, "application_match_confidence")
    status_confidence = _effective_status_confidence(payload, context)
    threshold = (
        UNCHANGED_CONFIRMATION_CONFIDENCE
        if current_status and status == current_status
        else STATUS_CHANGE_CONFIDENCE
    )
    if payload.get("matched_application") is not True or status not in ALLOWED_STATUSES:
        return None
    if match_confidence < threshold or status_confidence < threshold:
        return None
    if not evidence or evidence.lower() not in context.lower():
        return None
    if not _has_explicit_offer_evidence(context, status, evidence):
        return None
    return {"status": status, "raw_status": evidence, "confidence": confidence}


def _llm_rejection_reason(payload: dict[str, Any], context: str, current_status: str) -> str:
    status = str(payload.get("normalized_status") or "").strip()
    evidence = str(payload.get("raw_status") or "").strip()
    overall = _confidence(payload, "confidence")
    match_confidence = _confidence(payload, "application_match_confidence")
    status_confidence = _effective_status_confidence(payload, context)
    if payload.get("matched_application") is not True:
        return "AI 判断页面中的岗位与当前求职记录不匹配"
    if status not in ALLOWED_STATUSES:
        return "AI 没有在页面中找到明确的投递状态"
    if not evidence or evidence.lower() not in context.lower():
        return "AI 给出的状态证据无法在页面原文中复核"
    if not _has_explicit_offer_evidence(context, status, evidence):
        return "页面只有孤立的 Offer 栏目或流程节点，没有明确的录用状态证据"
    threshold = (
        UNCHANGED_CONFIRMATION_CONFIDENCE
        if current_status and status == current_status
        else STATUS_CHANGE_CONFIDENCE
    )
    risk = "确认当前状态" if status == current_status else "更新投递状态"
    return (
        f"AI 候选状态为“{status}”（证据：{evidence}，综合置信度 {overall:.0%}，"
        f"岗位匹配 {match_confidence:.0%}，状态识别 {status_confidence:.0%}）；"
        f"{risk}要求两项置信度均不低于 {threshold:.0%}，因此未更新"
    )


def _evidence_excerpt(context: str, evidence: str, limit: int = 600) -> str:
    if not context.strip():
        return ""
    index = context.lower().find(evidence.lower()) if evidence else -1
    if index < 0:
        excerpt = context[:limit]
    else:
        padding = max(0, (limit - len(evidence)) // 2)
        excerpt = context[max(0, index - padding):index + len(evidence) + padding]
    excerpt = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[邮箱已隐藏]", excerpt)
    excerpt = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号已隐藏]", excerpt)
    return re.sub(r"\s+", " ", excerpt).strip()[:limit]


def classify_status_with_llm(context: str, record: dict[str, Any]) -> dict[str, Any]:
    """Classify an unknown site using the configured model, with cache and evidence checks."""
    # Imports stay lazy so browser follow-up still works when optional AI packages are absent.
    from backend.services.ai_runtime_service import build_ai_runtime
    from backend.services.ai_skill_service import _resolve_config
    from src.libs.ai_engine.skills.builtin import JobStatusClassifierSkill

    config = _resolve_config("", "", "", "")
    if not config["api_key"] and config["provider"].lower() != "ollama":
        raise ValueError("未配置可用的 AI 模型/API Key")
    skill = JobStatusClassifierSkill()
    bundle = build_ai_runtime(config, [skill], max_retries=1)
    result = bundle.runtime.execute(
        skill.metadata.name,
        {
            "page_context": context,
            "company": str(record.get("company") or "").strip(),
            "role": str(record.get("role") or "").strip(),
            "current_status": str(record.get("status") or "").strip(),
            "source_url": str(record.get("followup_url") or record.get("link") or "").strip(),
        },
        provider=config["provider"],
        model=config["model"],
    )
    payload = result.structured_output
    usage = {
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        "total_tokens": result.usage.total_tokens,
    }
    return {
        "status": payload["normalized_status"],
        "raw_status": payload["raw_status"],
        "confidence": payload["confidence"],
        "matched_application": payload["matched_application"],
        "application_match_confidence": payload.get("application_match_confidence"),
        "status_confidence": payload.get("status_confidence"),
        "reason": payload.get("reason", ""),
        "applications": payload.get("applications", []),
        "usage": usage,
        "cache_hit": result.cache_hit,
    }


def classify_application_status(
    page_text: str, matched_context: str, record: dict[str, Any],
) -> dict[str, Any]:
    status, evidence = extract_status(matched_context)
    role_text = str(record.get("role") or "")
    multi_target_record = bool(re.search(r"[,，、/；;\n]", role_text))
    normalized_page = re.sub(r"\s+", " ", page_text).lower()
    marker_positions = sorted({
        match.start()
        for _, markers in STATUS_RULES for marker in markers if len(marker) >= 2
        for match in re.finditer(re.escape(marker.lower()), normalized_page)
    })
    status_marker_hits = 0
    last_position = -100
    for position in marker_positions:
        if position - last_position > 12:
            status_marker_hits += 1
            last_position = position
    multi_preference_page = (
        ("志愿一" in page_text and ("志愿二" in page_text or "当前应聘职位" in page_text))
        or multi_target_record
        or status_marker_hits >= 2
    )
    if status and not multi_preference_page:
        return {
            "status": status, "raw_status": evidence, "parser": "local",
            "llm_used": False, "llm_confidence": None, "llm_usage": {}, "cache_hit": False,
        }
    if record.get("followup_ai_enabled", True) is False:
        return {"status": None, "raw_status": "", "parser": "none", "llm_used": False,
                "llm_confidence": None, "llm_usage": {}, "cache_hit": False,
                "fallback_error": "AI 兜底未启用"}
    llm_context = _llm_page_context(
        page_text, matched_context, str(record.get("company") or ""), str(record.get("role") or ""),
    )
    if not llm_context:
        return {"status": None, "raw_status": "", "parser": "none", "llm_used": False,
                "llm_confidence": None, "llm_usage": {}, "cache_hit": False,
                "fallback_error": "页面没有可解析文本"}
    try:
        result = classify_status_with_llm(llm_context, record)
        # Compatibility: injected/legacy classifiers returned only already-validated fields.
        if "matched_application" not in result:
            return {
                "status": result["status"], "raw_status": result["raw_status"], "parser": "llm",
                "llm_used": True, "llm_confidence": result["confidence"],
                "llm_usage": result["usage"], "cache_hit": result["cache_hit"],
            }
        applications = result.get("applications") or []
        if applications:
            details: list[dict[str, Any]] = []
            application_roles = [str(item.get("role") or "").strip() for item in applications]
            for application in applications:
                application_role = str(application.get("role") or "未命名岗位")
                app_payload = {
                    "matched_application": application.get("matched_target") is True,
                    "normalized_status": application.get("normalized_status", "unknown"),
                    "raw_status": application.get("raw_status", ""),
                    "confidence": application.get("confidence", 0),
                    "application_match_confidence": application.get("application_match_confidence"),
                    "status_confidence": application.get("status_confidence"),
                }
                terminal = _terminal_status_for_application(
                    llm_context, application_role, application_roles,
                )
                if terminal:
                    app_payload.update({
                        "normalized_status": terminal[0],
                        "raw_status": terminal[1],
                        "confidence": 1.0,
                        "status_confidence": 1.0,
                    })
                accepted = _validated_llm_result(
                    app_payload, llm_context, str(record.get("status") or ""),
                )
                details.append({
                    "role": application_role,
                    "status": str(app_payload.get("normalized_status") or "unknown"),
                    "raw_status": str(app_payload.get("raw_status") or ""),
                    "confidence": _confidence(app_payload, "confidence"),
                    "application_match_confidence": _confidence(app_payload, "application_match_confidence"),
                    "status_confidence": _effective_status_confidence(app_payload, llm_context),
                    "status_inferred_by_rule": _is_submission_receipt(
                        llm_context,
                        str(app_payload.get("normalized_status") or ""),
                        str(app_payload.get("raw_status") or ""),
                    ),
                    "matched_target": application.get("matched_target") is True,
                    "accepted": accepted is not None,
                    "reason": (
                        f"同一岗位记录出现“{terminal[1]}”，终态优先于历史投递节点"
                        if terminal else str(application.get("reason") or "")
                    ),
                    "evidence_excerpt": _evidence_excerpt(
                        llm_context,
                        application_role or str(app_payload.get("raw_status") or ""),
                        limit=300,
                    ),
                })
            accepted_details = [item for item in details if item["accepted"]]
            accepted_statuses = {item["status"] for item in accepted_details}
            if len(accepted_details) == len(details) and len(accepted_statuses) == 1:
                common_status = next(iter(accepted_statuses))
                evidence = "；".join(dict.fromkeys(item["raw_status"] for item in details if item["raw_status"]))
                confidence = min(item["confidence"] for item in details)
                return {
                    "status": common_status, "raw_status": evidence, "parser": "llm",
                    "llm_used": True, "llm_confidence": confidence,
                    "llm_usage": result["usage"], "cache_hit": result["cache_hit"],
                    "llm_candidate_status": common_status,
                    "llm_candidate_evidence": evidence,
                    "llm_application_confidence": min(item["application_match_confidence"] for item in details),
                    "llm_status_confidence": min(item["status_confidence"] for item in details),
                    "llm_evidence_excerpt": " | ".join(dict.fromkeys(
                        item["evidence_excerpt"] for item in details if item["evidence_excerpt"]
                    )),
                    "application_statuses": details,
                }
            summary = "；".join(
                f"{item['role']}：{item['status']}（{item['confidence']:.0%}）" for item in details
            )
            return {
                "status": None, "raw_status": "", "parser": "llm", "llm_used": True,
                "llm_confidence": min((item["confidence"] for item in details), default=0),
                "llm_usage": result["usage"], "cache_hit": result["cache_hit"],
                "llm_candidate_status": "多岗位",
                "llm_candidate_evidence": summary,
                "llm_application_confidence": min((item["application_match_confidence"] for item in details), default=0),
                "llm_status_confidence": min((item["status_confidence"] for item in details), default=0),
                "llm_evidence_excerpt": " | ".join(dict.fromkeys(
                    item["evidence_excerpt"] for item in details if item["evidence_excerpt"]
                )),
                "application_statuses": details,
                "fallback_error": f"识别到 {len(details)} 条并行申请，状态不一致或部分岗位未达到安全线；已保留明细，未覆盖汇总状态：{summary}",
            }
        payload = {
            "matched_application": result["matched_application"],
            "normalized_status": result["status"],
            "raw_status": result["raw_status"],
            "confidence": result["confidence"],
            "application_match_confidence": result.get("application_match_confidence"),
            "status_confidence": result.get("status_confidence"),
        }
        validated = _validated_llm_result(payload, llm_context, str(record.get("status") or ""))
        excerpt = _evidence_excerpt(llm_context, result["raw_status"])
        if not validated:
            return {
                "status": None, "raw_status": "", "parser": "none", "llm_used": True,
                "llm_confidence": result["confidence"], "llm_usage": result["usage"],
                "cache_hit": result["cache_hit"],
                "llm_candidate_status": result["status"],
                "llm_candidate_evidence": result["raw_status"],
                "llm_application_confidence": _confidence(payload, "application_match_confidence"),
                "llm_status_confidence": _confidence(payload, "status_confidence"),
                "llm_evidence_excerpt": excerpt,
                "fallback_error": _llm_rejection_reason(payload, llm_context, str(record.get("status") or "")),
            }
        return {
            "status": validated["status"], "raw_status": validated["raw_status"], "parser": "llm",
            "llm_used": True, "llm_confidence": validated["confidence"],
            "llm_usage": result["usage"], "cache_hit": result["cache_hit"],
            "llm_candidate_status": validated["status"],
            "llm_candidate_evidence": validated["raw_status"],
            "llm_application_confidence": _confidence(payload, "application_match_confidence"),
            "llm_status_confidence": _confidence(payload, "status_confidence"),
            "llm_evidence_excerpt": excerpt,
        }
    except Exception as exc:
        return {"status": None, "raw_status": "", "parser": "none", "llm_used": True,
                "llm_confidence": None, "llm_usage": {}, "cache_hit": False,
                "fallback_error": str(exc)}


def check_application(record: dict[str, Any], headless: bool = True) -> dict[str, Any]:
    portal_url = str(record.get("followup_url") or record.get("link") or "").strip()
    _validate_url(portal_url)
    platform = str(record.get("followup_platform") or detect_platform(portal_url))
    with _BROWSER_LOCK:
        session = _LOGIN_BROWSERS.get(platform)
        if session and session.get("process") and session["process"].poll() is None:
            return {"result": "login_in_progress", "connection_state": "browser_open", "checked_at": _now(), "message": "普通 Chrome 登录窗口仍在打开，请先关闭并完成登录确认"}
        driver = init_browser(headless=headless, user_data_dir=str(_profile_dir(platform)))
        try:
            from selenium.webdriver.support.ui import WebDriverWait

            driver.set_page_load_timeout(90)
            _activate_restored_portal_tab(driver, portal_url)
            driver.get(portal_url)
            WebDriverWait(driver, 30).until(lambda current: current.find_element("tag name", "body"))
            page_text = ""
            context = ""
            stable_context = ""
            stable_count = 0
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                page_text = driver.execute_script("return document.body ? document.body.innerText : ''") or ""
                lowered = page_text.lower()
                if any(marker.lower() in lowered for marker in VERIFY_MARKERS + LOGIN_MARKERS):
                    break
                context = application_context(page_text, str(record.get("company", "")), str(record.get("role", "")))
                if context and context == stable_context:
                    stable_count += 1
                    if stable_count >= 2:
                        break
                else:
                    stable_context, stable_count = context, 0
                time.sleep(1)
            lowered = page_text.lower()
            if any(marker.lower() in lowered for marker in VERIFY_MARKERS):
                return {"result": "verification_required", "connection_state": "verification_required", "checked_at": _now(), "message": "网站要求完成人机验证"}
            if any(marker.lower() in lowered for marker in LOGIN_MARKERS):
                return {"result": "login_required", "connection_state": "login_required", "checked_at": _now(), "message": "登录已失效，请重新连接"}
            context = context or application_context(page_text, str(record.get("company", "")), str(record.get("role", "")))
            classification = classify_application_status(page_text, context, record)
            status, evidence = classification["status"], classification["raw_status"]
            application_statuses = classification.get("application_statuses") or []
            if status:
                parser_name = "AI 兜底" if classification["parser"] == "llm" else "本地规则"
                message = f"{parser_name}识别到状态：{status}（原文：{evidence}）"
                result_name = "changed" if status != record.get("status") else "unchanged"
            elif application_statuses:
                summary = "；".join(
                    f"{item['role']}：{item['status']}" for item in application_statuses
                )
                message = f"AI 已识别 {len(application_statuses)} 个并行岗位：{summary}；状态不一致，未覆盖汇总状态"
                result_name = "multi_status"
            else:
                message = "页面已检查，本地规则未识别；AI 兜底失败：" + classification.get("fallback_error", "未知原因")
                result_name = "unknown"
            return {
                "result": result_name,
                "status": status,
                "raw_status": evidence,
                "connection_state": "connected",
                "checked_at": _now(),
                "evidence_url": driver.current_url,
                "page_title": driver.title,
                "message": message,
                **{key: classification[key] for key in (
                    "parser", "llm_used", "llm_confidence", "llm_usage", "cache_hit",
                    "llm_candidate_status", "llm_candidate_evidence",
                    "llm_application_confidence", "llm_status_confidence", "llm_evidence_excerpt",
                    "application_statuses",
                ) if key in classification},
            }
        finally:
            driver.quit()
