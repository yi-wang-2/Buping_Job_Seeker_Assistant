"""Local browser-session based application status follow-up.

The service never stores passwords or bypasses verification. A visible browser
is used for user-assisted login; scheduled checks reuse Chrome's own encrypted
profile data and stop when verification is required.
"""

from __future__ import annotations

import re
import json
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
    "generic": (),
}

LOGIN_MARKERS = ("请登录", "立即登录", "登录后查看", "手机号登录", "扫码登录", "账号登录", "账号密码", "sign in", "log in")
VERIFY_MARKERS = ("人机验证", "安全验证", "滑动验证", "验证码", "captcha", "verify you are human")
STATUS_RULES = (
    ("Offer", ("已录用", "录用通知", "offer")),
    ("HR面", ("hr面试", "hr 面试", "人力面试")),
    ("主管面", ("主管面试", "终面", "业务面试")),
    ("技术面", ("技术面试", "专业面试", "面试中", "进入面试")),
    ("笔试", ("笔试中", "待笔试", "在线测评", "测评中")),
    ("简历挂", ("不合适", "未通过", "流程终止", "已淘汰", "很遗憾")),
    ("简历筛选", ("hr初筛", "初筛", "筛选中", "简历筛选", "处理中", "待处理", "已投递", "投递成功")),
)
ALLOWED_STATUSES = {"简历筛选", "笔试", "技术面", "主管面", "HR面", "Offer", "泡池子", "简历挂"}
LLM_SKILL_NAME = "job_status_classifier"
LLM_SKILL_VERSION = "1.1.0"


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


def extract_status(page_text: str) -> tuple[str | None, str]:
    normalized = re.sub(r"\s+", " ", page_text).lower()
    progress = re.search(r"(?:当前进度|当前状态|申请状态|流程状态|应聘状态)\s*[:：]\s*([^\n]{1,60})", page_text, re.IGNORECASE)
    if progress:
        raw = progress.group(1).strip()
        raw_lower = raw.lower()
        progress_rules = (
            ("Offer", ("offer", "录用")),
            ("简历挂", ("淘汰", "未通过", "不合适", "终止")),
            ("HR面", ("hr面", "hr 面", "人力面")),
            ("主管面", ("主管面", "终面", "业务面")),
            ("技术面", ("技术面", "专业面", "面试")),
            ("笔试", ("笔试", "测评")),
            ("简历筛选", ("初筛", "筛选", "已投递", "处理中", "待处理")),
        )
        for status, markers in progress_rules:
            if any(marker.lower() in raw_lower for marker in markers):
                return status, raw
    for status, markers in STATUS_RULES:
        matched = next((marker for marker in markers if marker.lower() in normalized), None)
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


def _json_object(content: str) -> dict[str, Any]:
    fenced = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", content.strip(), flags=re.IGNORECASE)
    start, end = fenced.find("{"), fenced.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("AI 未返回 JSON 对象")
    value = json.loads(fenced[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("AI 返回格式错误")
    return value


def _validated_llm_result(payload: dict[str, Any], context: str) -> dict[str, Any] | None:
    status = str(payload.get("normalized_status") or "").strip()
    evidence = str(payload.get("raw_status") or "").strip()
    try:
        confidence = float(payload.get("confidence") or 0)
    except (TypeError, ValueError):
        return None
    if payload.get("matched_application") is not True or status not in ALLOWED_STATUSES or confidence < 0.85:
        return None
    if not evidence or evidence.lower() not in context.lower():
        return None
    return {"status": status, "raw_status": evidence, "confidence": confidence}


def classify_status_with_llm(context: str, record: dict[str, Any]) -> dict[str, Any]:
    """Classify an unknown site using the configured model, with cache and evidence checks."""
    # Imports stay lazy so browser follow-up still works when optional AI packages are absent.
    from backend.services.ai_skill_service import _resolve_config
    from src.libs.ai_engine.memory import SQLiteMemoryRepository
    from src.libs.ai_engine.models import LLMRequest, Message
    from src.libs.ai_engine.observability import JsonlTraceSink
    from src.libs.ai_engine.optimization import PromptCache, document_fingerprint
    from src.libs.ai_engine.providers import GatewayConfig, LLMGateway

    config = _resolve_config("", "", "", "")
    if not config["api_key"] and config["provider"].lower() != "ollama":
        raise ValueError("未配置可用的 AI 模型/API Key")
    system_prompt = (
        "你是招聘投递状态分类器。只能依据页面文本中目标企业和岗位对应的明确状态作答，禁止推测。"
        "招聘网站可能同时展示志愿一、志愿二和当前应聘职位，目标岗位也可能是用户使用的简称。"
        "如果页面只有一条申请记录且状态明显属于整条申请流程，不得仅因志愿名称不同而判定不匹配；"
        "如果页面有多条独立申请记录，则必须定位目标岗位对应的状态。"
        "例如‘待处理’且页面说明简历评估尚未结束，应归类为‘简历筛选’。"
        "返回且仅返回 JSON：matched_application(boolean), normalized_status(string), "
        "raw_status(string), confidence(number), reason(string)。normalized_status 只能是："
        "简历筛选、笔试、技术面、主管面、HR面、Offer、泡池子、简历挂、unknown。"
        "raw_status 必须逐字复制页面文本中的最短状态证据；无法确认时返回 unknown，置信度不得高于0.5。"
    )
    user_prompt = (
        f"目标企业：{str(record.get('company') or '').strip()}\n"
        f"目标岗位：{str(record.get('role') or '').strip()}\n"
        f"页面文本：\n{context}"
    )
    messages = (Message("system", system_prompt), Message("user", user_prompt))
    repository = SQLiteMemoryRepository()
    cache = PromptCache(repository.path) if repository.get_setting("cache_enabled", True) else None
    cache_key = PromptCache.key(
        provider=config["provider"], model=config["model"], skill=LLM_SKILL_NAME,
        skill_version=LLM_SKILL_VERSION, messages=[message.as_dict() for message in messages],
        parameters={"temperature": 0, "max_output_tokens": 300},
    )
    response = cache.get(cache_key) if cache else None
    cache_hit = response is not None
    if response is None:
        gateway = LLMGateway(
            GatewayConfig(api_key=config["api_key"], base_url=config["base_url"], max_retries=1),
            trace_sink=JsonlTraceSink(),
        )
        response = gateway.invoke(LLMRequest(
            messages=messages, provider=config["provider"], model=config["model"],
            temperature=0, max_output_tokens=300,
            metadata={"skill": LLM_SKILL_NAME, "skill_version": LLM_SKILL_VERSION},
        ))
    usage = {
        "input_tokens": 0 if cache_hit else response.usage.input_tokens,
        "output_tokens": 0 if cache_hit else response.usage.output_tokens,
        "total_tokens": 0 if cache_hit else response.usage.total_tokens,
    }
    payload = _json_object(response.content)
    validated = _validated_llm_result(payload, context)
    if not validated:
        repository.record_skill_run(
            skill_name=LLM_SKILL_NAME, skill_version=LLM_SKILL_VERSION,
            input_hash=document_fingerprint(user_prompt), model=config["model"],
            usage=usage, cache_hit=cache_hit, status="error", error_code="unverified_status",
        )
        status = str(payload.get("normalized_status") or "").strip()
        evidence = str(payload.get("raw_status") or "").strip()
        try:
            confidence = float(payload.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0
        if payload.get("matched_application") is not True:
            reason = "AI 判断页面中的岗位与当前求职记录不匹配"
        elif status not in ALLOWED_STATUSES:
            reason = "AI 没有在页面中找到明确的投递状态"
        elif confidence < 0.85:
            reason = f"AI 识别置信度仅为 {confidence:.0%}，低于 85% 安全线"
        elif not evidence or evidence.lower() not in context.lower():
            reason = "AI 给出的状态证据无法在页面原文中复核"
        else:
            reason = "AI 返回结果未通过安全校验"
        raise ValueError(reason)
    if cache and not cache_hit:
        cache.put(cache_key, response, ttl_seconds=7 * 86400)
    repository.record_skill_run(
        skill_name=LLM_SKILL_NAME, skill_version=LLM_SKILL_VERSION,
        input_hash=document_fingerprint(user_prompt), model=config["model"],
        usage=usage, cache_hit=cache_hit,
    )
    return {**validated, "usage": usage, "cache_hit": cache_hit}


def classify_application_status(
    page_text: str, matched_context: str, record: dict[str, Any],
) -> dict[str, Any]:
    status, evidence = extract_status(matched_context)
    multi_preference_page = "志愿一" in page_text and ("志愿二" in page_text or "当前应聘职位" in page_text)
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
        return {
            "status": result["status"], "raw_status": result["raw_status"], "parser": "llm",
            "llm_used": True, "llm_confidence": result["confidence"],
            "llm_usage": result["usage"], "cache_hit": result["cache_hit"],
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
            if status:
                parser_name = "AI 兜底" if classification["parser"] == "llm" else "本地规则"
                message = f"{parser_name}识别到状态：{status}（原文：{evidence}）"
            else:
                message = "页面已检查，本地规则未识别；AI 兜底失败：" + classification.get("fallback_error", "未知原因")
            return {
                "result": "changed" if status and status != record.get("status") else "unchanged",
                "status": status,
                "raw_status": evidence,
                "connection_state": "connected",
                "checked_at": _now(),
                "evidence_url": driver.current_url,
                "page_title": driver.title,
                "message": message,
                **{key: classification[key] for key in (
                    "parser", "llm_used", "llm_confidence", "llm_usage", "cache_hit"
                )},
            }
        finally:
            driver.quit()
