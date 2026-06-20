"""Interview preparation and mock interview service."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.services.config_service import load_secrets

import config as cfg

DATA_FOLDER = Path("data_folder")
OUTPUT_FOLDER = DATA_FOLDER / "output"


def _get_effective_config(api_key: str = "", model_type: str = "", base_url: str = "") -> dict[str, str]:
    """Resolve effective LLM config from args > secrets > config.py."""
    secrets = load_secrets()
    return {
        "api_key": api_key or secrets.get("llm_api_key", "") or cfg.ANTHROPIC_AUTH_TOKEN,
        "model_type": model_type or secrets.get("llm_model_type", "anthropic"),
        "base_url": base_url or secrets.get("llm_base_url", "") or cfg.ANTHROPIC_BASE_URL,
    }


def generate_interview_prep(
    api_key: str,
    model_type: str,
    base_url: str,
    job_description: str,
    interview_type: str = "综合面试",
    question_count: int = 10,
    resume_language: str = "zh",
) -> dict[str, Any]:
    """Generate interview preparation report. Returns {report, file_path, status}."""
    from src.libs.interview_prep import InterviewPrepGenerator

    effective = _get_effective_config(api_key, model_type, base_url)

    resume_file = DATA_FOLDER / ("plain_text_resume.yaml" if resume_language == "en" else "plain_text_resume_zh.yaml")
    with open(resume_file, "r", encoding="utf-8") as f:
        resume_text = f.read()

    generator = InterviewPrepGenerator(
        api_key=effective["api_key"],
        model_type=effective["model_type"],
        base_url=effective["base_url"],
    )
    report = generator.generate(
        resume_text=resume_text,
        job_description=job_description or "",
        interview_type=interview_type,
        question_count=int(question_count),
        language=resume_language,
    )

    output_dir = OUTPUT_FOLDER / "interview_prep"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"interview_prep_{timestamp}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    return {"report": report, "file_path": str(output_path), "status": "success"}


# In-memory mock interview sessions
_sessions: dict[str, Any] = {}


def start_mock_interview(
    api_key: str,
    model_type: str,
    base_url: str,
    resume_text: str,
    job_description: str,
    company_name: str = "",
    company_industry: str = "",
    job_title: str = "",
    interview_type: str = "综合面试",
    interview_style: str = "专业型",
) -> dict[str, Any]:
    """Start a mock interview session. Returns {history, session_id, status}."""
    from src.libs.interview_prep import (
        MockInterviewer,
        CandidateProfile,
        CompanyProfile,
        JobProfile,
        InterviewStyle,
    )

    effective = _get_effective_config(api_key, model_type, base_url)

    if not resume_text.strip():
        return {"history": [], "session_id": None, "status": "❌ 请先提供简历内容"}
    if not job_description.strip():
        return {"history": [], "session_id": None, "status": "❌ 请先提供职位描述 (JD)"}

    candidate = CandidateProfile(name="候选人", resume_text=resume_text, target_position=job_title or "应聘岗位")
    company = CompanyProfile(name=company_name or "某公司", industry=company_industry or "", culture="")
    job = JobProfile(title=job_title or "应聘岗位", description=job_description)

    style_map = {
        "友善型": InterviewStyle.FRIENDLY,
        "专业型": InterviewStyle.PROFESSIONAL,
        "压力型": InterviewStyle.PRESSURE,
        "学术型": InterviewStyle.ACADEMIC,
        "闲聊型": InterviewStyle.CASUAL,
    }
    style_enum = style_map.get(interview_style, InterviewStyle.PROFESSIONAL)

    interviewer = MockInterviewer(
        api_key=effective["api_key"],
        model_type=effective["model_type"],
        base_url=effective["base_url"],
    )
    session = interviewer.start_session(
        candidate=candidate,
        company=company,
        job=job,
        interview_type=interview_type,
        style=style_enum,
    )

    # Store session for later use
    _sessions[session.session_id] = {
        "interviewer": interviewer,
        "session": session,
        "config": {
            "api_key": effective["api_key"],
            "model_type": effective["model_type"],
            "base_url": effective["base_url"],
            "resume_text": resume_text,
            "job_description": job_description,
            "company_name": company_name,
            "company_industry": company_industry,
            "job_title": job_title,
            "interview_type": interview_type,
            "interview_style": interview_style,
        },
    }

    history = [{"role": "assistant", "content": session.messages[0].content}] if session.messages else []
    return {"history": history, "session_id": session.session_id, "status": "✅ 面试已开始！"}


def submit_mock_answer(
    session_id: str,
    user_message: str,
    history: list[dict],
) -> dict[str, Any]:
    """Submit an answer in a mock interview. Returns {history, session_id, status}."""
    from src.libs.interview_prep.mock_interview import InterviewMessage, InterviewRound

    if not session_id or session_id not in _sessions:
        return {"history": history, "session_id": session_id, "status": "❌ 请先开始面试"}
    if not user_message.strip():
        return {"history": history, "session_id": session_id, "status": "❌ 请输入回答"}

    stored = _sessions[session_id]
    interviewer = stored["interviewer"]

    # Re-create session from history for stateless call
    from src.libs.interview_prep import MockInterviewSession
    session = MockInterviewSession(
        session_id=session_id,
        candidate=interviewer.sessions[session_id].candidate,
        company=interviewer.sessions[session_id].company,
        job=interviewer.sessions[session_id].job,
        interview_type=stored["config"]["interview_type"],
        style=interviewer.sessions[session_id].style,
    )
    for entry in history:
        role = entry.get("role", "")
        content = entry.get("content", "")
        if role == "user" and content:
            session.messages.append(InterviewMessage(role="candidate", content=content, timestamp=time.time(), round=InterviewRound.OPENING))
        elif role == "assistant" and content:
            session.messages.append(InterviewMessage(role="interviewer", content=content, timestamp=time.time(), round=InterviewRound.OPENING))

    interviewer.sessions[session_id] = session
    next_question_msg = interviewer.submit_answer(session_id, user_message)

    new_history = list(history) + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": next_question_msg.content},
    ]
    return {"history": new_history, "session_id": session_id, "status": "✅ 已收到回答"}


def end_mock_interview(session_id: str, history: list[dict]) -> dict[str, Any]:
    """End a mock interview and generate evaluation. Returns {evaluation, file_path, status}."""
    from src.libs.interview_prep import MockInterviewSession
    from src.libs.interview_prep.mock_interview import InterviewMessage, InterviewRound

    if not session_id or session_id not in _sessions:
        return {"evaluation": "❌ 没有进行中的面试", "file_path": "", "status": "error"}

    stored = _sessions[session_id]
    interviewer = stored["interviewer"]
    config = stored["config"]

    # Restore session
    session = MockInterviewSession(
        session_id=session_id,
        candidate=interviewer.sessions[session_id].candidate,
        company=interviewer.sessions[session_id].company,
        job=interviewer.sessions[session_id].job,
        interview_type=config["interview_type"],
        style=interviewer.sessions[session_id].style,
    )
    for entry in history:
        role = entry.get("role", "")
        content = entry.get("content", "")
        if role == "user" and content:
            session.messages.append(InterviewMessage(role="candidate", content=content, timestamp=time.time(), round=InterviewRound.OPENING))
        elif role == "assistant" and content:
            session.messages.append(InterviewMessage(role="interviewer", content=content, timestamp=time.time(), round=InterviewRound.OPENING))
    interviewer.sessions[session_id] = session

    evaluation = interviewer.end_session(session_id)

    # Save report
    output_dir = OUTPUT_FOLDER / "mock_interview"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"interview_eval_{timestamp}.md"

    full_report = f"""# 模拟面试评估报告

**时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**岗位**: {config.get("job_title", "")}
**公司**: {config.get("company_name", "")}

---

## 面试对话记录

"""
    for entry in history:
        role = entry.get("role", "")
        content = entry.get("content", "")
        if role == "user" and content:
            full_report += f"**候选人**: {content}\n\n"
        elif role == "assistant" and content:
            full_report += f"**面试官**: {content}\n\n"

    full_report += f"---\n\n## 评估报告\n\n{evaluation}"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_report)

    # Cleanup
    del _sessions[session_id]

    return {"evaluation": evaluation, "file_path": str(output_path), "status": "success"}
