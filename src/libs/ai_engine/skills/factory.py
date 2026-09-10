from __future__ import annotations

from .builtin import (
    CareerAdvisorSkill,
    InterviewCoachSkill,
    JDAnalyzerSkill,
    JobStatusClassifierSkill,
    JobRecommenderSkill,
    DirectChatSkill,
    MockInterviewerSkill,
    ResumeReviewerSkill,
    ResumeWriterSkill,
    SkillMatcherSkill,
    TextRewriterSkill,
)
from .registry import SkillRegistry


def create_builtin_registry(rewrite_prompts: dict[str, dict[str, str]] | None = None) -> SkillRegistry:
    registry = SkillRegistry()
    for skill in (
        TextRewriterSkill(rewrite_prompts), JDAnalyzerSkill(), InterviewCoachSkill(),
        MockInterviewerSkill(), ResumeWriterSkill(), ResumeReviewerSkill(), SkillMatcherSkill(), CareerAdvisorSkill(),
        JobStatusClassifierSkill(), JobRecommenderSkill(), DirectChatSkill(),
    ):
        registry.register(skill)
    return registry

