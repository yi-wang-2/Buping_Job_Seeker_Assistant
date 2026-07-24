import pytest

from src.libs.ai_engine.skills import SkillRegistry
from src.libs.ai_engine.skills.builtin import JDAnalyzerSkill


def test_registry_registers_and_rejects_duplicates():
    registry = SkillRegistry()
    skill = JDAnalyzerSkill()
    registry.register(skill)

    assert registry.get("jd_analyzer") is skill
    with pytest.raises(ValueError):
        registry.register(skill)

