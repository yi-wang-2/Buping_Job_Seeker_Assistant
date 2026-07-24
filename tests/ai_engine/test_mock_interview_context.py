import time

from src.libs.interview_prep.mock_interview import (
    CandidateProfile, CompanyProfile, InterviewMessage, InterviewRound,
    JobProfile, MockInterviewSession, _build_dialogue_prompt,
)


def test_mock_interview_context_is_budgeted_and_chronological():
    session = MockInterviewSession(
        session_id="test",
        candidate=CandidateProfile(resume_text="Python 开发经验"),
        company=CompanyProfile(name="测试公司"),
        job=JobProfile(title="Python 工程师", description="负责后端服务"),
        context_window=2,
    )
    base = time.time()
    for index in range(8):
        session.messages.append(InterviewMessage(
            role="candidate" if index % 2 else "interviewer",
            content=f"消息 {index}", timestamp=base + index,
            round=InterviewRound.TECHNICAL,
        ))

    prompt = _build_dialogue_prompt(session).text

    assert "消息 0" not in prompt
    assert prompt.index("消息 3") < prompt.index("消息 7")
    assert session.last_context_metrics["context_final_tokens"] > 0
    assert session.last_context_metrics["context_items_kept"] <= 6
