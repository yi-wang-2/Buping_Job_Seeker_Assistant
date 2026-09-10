from __future__ import annotations

from typing import Any

from ....presentation import CalloutBlock, DetailItem, DetailListBlock, FollowUpBlock, HeadingBlock, ResponseDocument


class JobRecommendationPresenter:
    def present(self, output: Any, *, inputs: dict[str, Any]) -> ResponseDocument:
        data = dict(output or {})
        zh = inputs.get("language") != "en"
        jobs = {str(item.get("id")): item for item in inputs.get("jobs", [])}
        details = []
        for index, recommendation in enumerate(data.get("recommendations", []), start=1):
            job = jobs.get(str(recommendation.get("job_id")), {})
            company = str(job.get("company") or ("未知企业" if zh else "Unknown company"))
            role = str(job.get("role") or ("招聘岗位" if zh else "Open role"))
            score = job.get("match_score", job.get("score"))
            label_parts = [str(job.get("location") or ""), str(job.get("recruitment_type") or "")]
            if score not in (None, ""):
                label_parts.append(f"匹配度 {score}%" if zh else f"Match {score}%")
            highlights = [str(item) for item in recommendation.get("fit_highlights", []) if str(item).strip()]
            cautions = [str(item) for item in recommendation.get("cautions", []) if str(item).strip()]
            body = str(recommendation.get("reason") or "")
            if highlights:
                body += ("\n\n匹配点：" if zh else "\n\nFit: ") + "；".join(highlights)
            if cautions:
                body += ("\n\n注意：" if zh else "\n\nWatch: ") + "；".join(cautions)
            details.append(DetailItem(
                title=f"{index}. {company}｜{role}",
                label=" · ".join(part for part in label_parts if part),
                body=body,
                quote=str(job.get("link") or ""),
            ))
        return ResponseDocument((
            HeadingBlock("岗位推荐" if zh else "Job recommendations"),
            CalloutBlock(str(data.get("summary") or ("已按当前偏好完成排序。" if zh else "Ranked using your current preferences."))),
            DetailListBlock(tuple(details), ordered=False),
            FollowUpBlock(
                "你可以告诉我想收藏、屏蔽或加入投递记录的岗位。" if zh
                else "Tell me which role you want to favorite, hide, or add to your application tracker."
            ),
        ))
