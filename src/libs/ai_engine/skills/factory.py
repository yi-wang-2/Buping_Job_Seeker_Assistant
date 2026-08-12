from __future__ import annotations

from .builtin import (
    CareerAdvisorSkill,
    InterviewCoachSkill,
    JDAnalyzerSkill,
    JobStatusClassifierSkill,
    MockInterviewerSkill,
    ResumeWriterSkill,
    SkillMatcherSkill,
    TextRewriterSkill,
)
from .registry import SkillRegistry


def create_builtin_registry(rewrite_prompts: dict[str, dict[str, str]] | None = None) -> SkillRegistry:
    registry = SkillRegistry()
    for skill in (
        TextRewriterSkill(rewrite_prompts), JDAnalyzerSkill(), InterviewCoachSkill(),
        MockInterviewerSkill(), ResumeWriterSkill(), SkillMatcherSkill(), CareerAdvisorSkill(),
        JobStatusClassifierSkill(),
    ):
        registry.register(skill)
    return registry

