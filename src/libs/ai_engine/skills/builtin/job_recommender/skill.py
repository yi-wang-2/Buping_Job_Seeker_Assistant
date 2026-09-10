from __future__ import annotations

import json
import re
from typing import Any

from ....context import ContextItem, ContextKind, TokenBudget
from ....models import LLMResponse, Message
from ...base import SkillMetadata, SkillResult
from ...schemas import JobRecommenderInput, JobRecommendationOutput
from .presenter import JobRecommendationPresenter


class JobRecommenderSkill:
    presenter = JobRecommendationPresenter()
    metadata = SkillMetadata(
        name="job_recommender",
        version="1.0.0",
        description="Rank visible jobs against explicit user preferences with an ID-grounded result.",
        token_budget=TokenBudget(24000, 3500, 1800, 800),
        tags=("job", "recommendation", "grounded"),
        input_schema=JobRecommenderInput,
        output_schema=JobRecommendationOutput,
        prompt_version="1",
        temperature=.2,
        cacheable=False,
        context_weights={"system": .15, "request": .10, "task": .75},
    )

    SYSTEM = """你是岗位推荐分析器。根据用户明确求职偏好和候选岗位字段，对候选岗位进行语义比较并推荐最合适的岗位。
只能从候选列表选择 job_id，不得编造岗位、企业、地点、分数或链接。优先考虑目标岗位、技能方向、地点、招聘类型、行业和用户排除项；match_score 是已有特征评分，可参考但不能替代语义判断。理由要具体说明岗位与偏好的对应关系，信息不足时明确不确定性。
只输出 JSON：{"summary":"...","recommendations":[{"job_id":"...","reason":"...","fit_highlights":["..."],"cautions":["..."]}]}。推荐数量不得超过输入 limit，不得重复 job_id。"""

    def validate_input(self, inputs: dict[str, Any]) -> None:
        if not inputs.get("jobs"):
            raise ValueError("No visible jobs are available for recommendation")

    def context_items(self, inputs: dict[str, Any]) -> list[ContextItem]:
        compact_jobs = [{
            "id": item.get("id"), "company": item.get("company"), "role": item.get("role"),
            "location": item.get("location"), "recruitment_type": item.get("recruitment_type"),
            "match_score": item.get("match_score", item.get("score")), "industry": item.get("industry"),
            "company_type": item.get("company_type"),
        } for item in inputs["jobs"]]
        return [
            ContextItem("job-recommender-system", ContextKind.SYSTEM, self.SYSTEM, "skill", protected=True, priority=100, relevance=1),
            ContextItem("job-recommender-request", ContextKind.REQUEST, json.dumps({
                "query": inputs.get("query"), "limit": inputs.get("limit"),
                "language": inputs.get("language"), "preferences": inputs.get("preferences", {}),
            }, ensure_ascii=False), "user", protected=True, priority=100, relevance=1),
            ContextItem("job-recommender-candidates", ContextKind.TASK, json.dumps(compact_jobs, ensure_ascii=False),
                        "job_radar", protected=True, priority=100, relevance=1),
        ]

    def build_messages(self, inputs: dict[str, Any], context: tuple[ContextItem, ...]) -> tuple[Message, ...]:
        by_id = {item.id: item.content for item in context}
        return (
            Message("system", by_id["job-recommender-system"]),
            Message("user", f"请求与偏好：\n{by_id['job-recommender-request']}\n\n候选岗位：\n{by_id['job-recommender-candidates']}"),
        )

    def parse_output(self, response: LLMResponse) -> SkillResult:
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.content.strip(), flags=re.IGNORECASE)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                raise
            payload = json.loads(match.group(0))
        return SkillResult(content=raw, structured_output=payload, usage=response.usage)

    def validate_output(self, result: SkillResult, inputs: dict[str, Any]) -> None:
        output = JobRecommendationOutput.model_validate(result.structured_output)
        jobs = {str(item.get("id")): item for item in inputs["jobs"]}
        seen: set[str] = set()
        grounded = []
        for item in output.recommendations:
            if item.job_id not in jobs:
                raise ValueError(f"Recommendation references unknown job_id: {item.job_id}")
            if item.job_id in seen:
                continue
            seen.add(item.job_id)
            grounded.append(item.model_dump())
            if len(grounded) >= int(inputs.get("limit", 10)):
                break
        requested = min(int(inputs.get("limit", 10)), len(jobs))
        if len(grounded) < requested:
            remaining = sorted(
                (item for key, item in jobs.items() if key not in seen),
                key=lambda item: float(item.get("match_score", item.get("score", 0)) or 0),
                reverse=True,
            )
            for job in remaining[:requested - len(grounded)]:
                job_id = str(job.get("id"))
                score = job.get("match_score", job.get("score"))
                grounded.append({
                    "job_id": job_id,
                    "reason": f"当前岗位库综合匹配分为 {score}，作为补充候选。",
                    "fit_highlights": [],
                    "cautions": ["模型未完整返回要求数量，建议打开岗位原文进一步确认。"],
                })
                seen.add(job_id)
        if not grounded:
            raise ValueError("Job recommendation did not contain any grounded candidate")
        result.structured_output["recommendations"] = grounded

    def extract_memories(self, result: SkillResult, inputs: dict[str, Any]) -> tuple[Any, ...]:
        return ()
