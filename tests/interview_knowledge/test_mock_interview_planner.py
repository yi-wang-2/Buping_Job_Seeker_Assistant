from src.libs.interview_prep.mock_interview import (
    CandidateProfile,
    CompanyProfile,
    JobProfile,
    MockInterviewSession,
    _build_system_prompt,
    _plan_next_question,
)


def _session():
    return MockInterviewSession(
        session_id="session-1",
        candidate=CandidateProfile(resume_text="负责 Agent 项目"),
        company=CompanyProfile(name="示例公司"),
        job=JobProfile(title="AI 工程师", description="RAG 与系统设计"),
        interview_blueprint={"competency_weights": {"ai": .7, "system_design": .3}},
        competency_state={
            "ai": {"turns": 0, "depth": 0.0},
            "system_design": {"turns": 0, "depth": 0.0},
        },
        question_pool=[
            {
                "unit_id": "q-ai", "question": "如何评估 RAG？",
                "competencies": ["ai"], "interviewer_intent": "评测能力",
                "rubric": ["指标", "数据集"],
            },
            {
                "unit_id": "q-system", "question": "如何设计高可用服务？",
                "competencies": ["system_design"], "interviewer_intent": "架构能力",
                "rubric": ["故障域"],
            },
        ],
    )


def test_planner_snapshots_cards_and_does_not_repeat_them():
    session = _session()

    first = _plan_next_question(session)
    second = _plan_next_question(session, "我做过项目，但没有说明指标")

    assert first["unit_id"] != second["unit_id"]
    assert len(session.asked_unit_ids) == 2
    assert session.competency_state[first["competency"]]["turns"] == 1


def test_planner_adjusts_difficulty_from_answer_depth():
    session = _session()
    session.interview_blueprint = {"competency_weights": {"ai": 1.0}}
    session.competency_state = {"ai": {"turns": 0, "depth": 0.0}}
    _plan_next_question(session)

    short = _plan_next_question(session, "不清楚")
    assert short["difficulty"] == "introductory"

    session.last_question_plan = {"competency": "ai"}
    detailed = _plan_next_question(
        session,
        "我负责项目评测，因为线上需要量化结果。例如我们用固定数据集比较命中率、"
        "事实一致性和 P95 延迟，并讨论了成本取舍与失败案例。" * 3,
    )
    assert detailed["difficulty"] == "advanced"


def test_prompt_contains_plan_but_not_reference_answer():
    session = _session()
    plan = _plan_next_question(session)
    prompt = _build_system_prompt(session)

    assert plan["question_seed"] in prompt
    assert "题卡只提供提问方向" in prompt
    assert "reference_answer" not in prompt
