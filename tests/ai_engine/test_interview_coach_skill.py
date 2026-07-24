from src.libs.ai_engine.context import ContextManager, TokenBudgetAllocator
from src.libs.ai_engine.skills.builtin import InterviewCoachSkill


def test_interview_coach_preserves_prepared_report_prompt():
    skill = InterviewCoachSkill()
    prompt = "# 第一部分：岗位分析\n\n简历证据：Python 3 年\n\n# 第二部分：面试准备报告"
    inputs = {
        "resume": "Python 3 年",
        "job_description": "Python 工程师",
        "prepared_prompt": prompt,
    }
    allocation = TokenBudgetAllocator().allocate(skill.metadata.token_budget, skill.metadata.context_weights)
    bundle = ContextManager().build(skill.context_items(inputs), allocation)
    messages = skill.build_messages(inputs, bundle.items)

    assert messages[1].content == prompt
    assert "不得虚构" in messages[0].content
