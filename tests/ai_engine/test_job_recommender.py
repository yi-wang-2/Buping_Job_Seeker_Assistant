import pytest

from src.libs.ai_engine.models import LLMResponse, TokenUsage
from src.libs.ai_engine.skills.builtin import JobRecommenderSkill


def _inputs():
    return {
        "query": "推荐两个岗位",
        "preferences": {"target_roles": ["AI Agent开发"]},
        "jobs": [
            {"id": "a", "company": "甲", "role": "Agent开发", "match_score": 95},
            {"id": "b", "company": "乙", "role": "后端开发", "match_score": 70},
        ],
        "limit": 2,
        "language": "zh",
    }


def test_job_recommender_keeps_only_unique_grounded_ids():
    skill = JobRecommenderSkill()
    result = skill.parse_output(LLMResponse(
        content='{"summary":"优先 Agent 岗位","recommendations":['
                '{"job_id":"a","reason":"方向匹配","fit_highlights":[],"cautions":[]},'
                '{"job_id":"a","reason":"重复","fit_highlights":[],"cautions":[]},'
                '{"job_id":"b","reason":"备选","fit_highlights":[],"cautions":[]}]}',
        provider="test", model="test", usage=TokenUsage(total_tokens=10),
    ))
    skill.validate_output(result, _inputs())
    assert [item["job_id"] for item in result.structured_output["recommendations"]] == ["a", "b"]


def test_job_recommender_fills_missing_requested_candidates_from_grounded_scores():
    skill = JobRecommenderSkill()
    result = skill.parse_output(LLMResponse(
        content='{"summary":"结果","recommendations":['
                '{"job_id":"a","reason":"方向匹配","fit_highlights":[],"cautions":[]}]}',
        provider="test", model="test", usage=TokenUsage(total_tokens=10),
    ))
    skill.validate_output(result, _inputs())
    assert [item["job_id"] for item in result.structured_output["recommendations"]] == ["a", "b"]


def test_job_recommender_rejects_hallucinated_job_id():
    skill = JobRecommenderSkill()
    result = skill.parse_output(LLMResponse(
        content='{"summary":"结果","recommendations":['
                '{"job_id":"missing","reason":"虚构","fit_highlights":[],"cautions":[]}]}',
        provider="test", model="test", usage=TokenUsage(total_tokens=10),
    ))
    with pytest.raises(ValueError, match="unknown job_id"):
        skill.validate_output(result, _inputs())
