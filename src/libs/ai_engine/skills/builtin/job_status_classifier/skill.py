from __future__ import annotations

import json
import re
from typing import Any

from ....context import ContextItem, ContextKind, TokenBudget
from ....models import LLMResponse, Message
from ...base import SkillMetadata, SkillResult
from ...schemas import JobStatusClassification, JobStatusClassifierInput


ALLOWED_CONFIDENT_STATUSES = {
    "简历筛选", "笔试", "技术面", "主管面", "HR面", "Offer", "泡池子", "简历挂",
}


class JobStatusClassifierSkill:
    metadata = SkillMetadata(
        name="job_status_classifier",
        version="2.5.0",
        description="Classify an application status from verifiable portal text.",
        token_budget=TokenBudget(
            model_context_limit=12000, reserved_output=1200,
            reserved_system=1200, safety_margin=500,
        ),
        tags=("job", "followup", "classification"),
        input_schema=JobStatusClassifierInput,
        output_schema=JobStatusClassification,
        temperature=0,
        cache_ttl_seconds=7 * 86400,
        context_weights={"system": .18, "task": .82},
    )

    SYSTEM = (
        "你是招聘投递状态分类器。只能依据页面文本中目标企业和岗位对应的明确状态作答，禁止推测。"
        "招聘网站可能同时展示志愿一、志愿二和当前应聘职位，目标企业和岗位也可能是简称或语义相近的正式名称。"
        "目标岗位中使用逗号、顿号、斜杠分隔的内容表示多个可接受意向，匹配其中一个即可。"
        "同一企业页面可能允许同时投递多个岗位。此时必须逐条识别所有可见申请，禁止只挑一条概括。"
        "在‘应聘记录’、‘投递记录’或‘申请记录’列表中，‘投递简历’、‘内推投递’表示企业已经收到简历，"
        "应归类为‘简历筛选’，status_confidence 应不低于 0.95；职位详情页上的同名投递按钮不适用此规则。"
        "同一岗位记录同时出现历史节点和最新状态时，必须采用最新且更终局的状态；"
        "例如‘投递简历 ... 流程终止’必须归类为‘简历挂’，raw_status 为‘流程终止’，禁止仍归类为简历筛选。"
        "如果页面只有一条申请记录且状态明显属于整条申请流程，不得仅因志愿名称不同而判定不匹配；"
        "如果页面有多条独立申请记录，则必须定位目标岗位对应的状态。"
        "例如‘待处理’且页面说明简历评估尚未结束，应归类为‘简历筛选’。"
        "返回且仅返回 JSON：matched_application(boolean), normalized_status(string), raw_status(string), "
        "confidence(number), application_match_confidence(number), status_confidence(number), reason(string), applications(array)。"
        "applications 中每项包含 role, matched_target, normalized_status, raw_status, confidence, "
        "application_match_confidence, status_confidence, reason；页面有几条申请就返回几项。"
        "若存在多条申请且状态不同，顶层 normalized_status 必须为 unknown，raw_status 为空；"
        "若所有申请状态一致，顶层可以返回共同状态。"
        "application_match_confidence 只衡量页面记录是否属于目标申请；status_confidence 只衡量状态文字是否明确；"
        "confidence 是二者的保守综合值。normalized_status 只能是："
        "简历筛选、笔试、技术面、主管面、HR面、Offer、泡池子、简历挂、unknown。"
        "raw_status 必须逐字复制页面文本中的最短状态证据；无法确认时返回 unknown，置信度不得高于0.5。"
    )

    def validate_input(self, inputs: dict[str, Any]) -> None:
        if not str(inputs.get("page_context", "")).strip():
            raise ValueError("Page context cannot be empty")

    def context_items(self, inputs: dict[str, Any]) -> list[ContextItem]:
        prompt = (
            f"目标企业：{str(inputs.get('company') or '').strip()}\n"
            f"目标岗位：{str(inputs.get('role') or '').strip()}\n"
            f"系统当前状态：{str(inputs.get('current_status') or '').strip()}\n"
            f"申请页面链接：{str(inputs.get('source_url') or '').strip()}\n"
            f"页面文本：\n{inputs['page_context']}"
        )
        return [
            ContextItem("job-status-system", ContextKind.SYSTEM, self.SYSTEM, "skill",
                        protected=True, priority=100, relevance=1),
            ContextItem("job-status-page", ContextKind.TASK, prompt, "browser_page",
                        protected=True, priority=100, relevance=1),
        ]

    def build_messages(self, inputs: dict[str, Any], context: tuple[ContextItem, ...]) -> tuple[Message, ...]:
        by_id = {item.id: item.content for item in context}
        return Message("system", by_id["job-status-system"]), Message("user", by_id["job-status-page"])

    def parse_output(self, response: LLMResponse) -> SkillResult:
        fenced = re.sub(
            r"^\s*```(?:json)?\s*|\s*```\s*$", "", response.content.strip(), flags=re.IGNORECASE,
        )
        start, end = fenced.find("{"), fenced.rfind("}")
        if start < 0 or end <= start:
            suffix = "（模型输出可能被截断）" if response.finish_reason in {"length", "max_tokens"} else ""
            raise ValueError(f"AI 未返回完整 JSON 对象{suffix}")
        raw = fenced[start:end + 1]
        repaired = False
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as original_error:
            candidate = self._repair_common_json_syntax(raw)
            try:
                payload = json.loads(candidate)
                repaired = True
                raw = candidate
            except json.JSONDecodeError as repaired_error:
                suffix = "，模型输出可能被截断" if response.finish_reason in {"length", "max_tokens"} else ""
                raise ValueError(
                    f"AI 返回的 JSON 语法错误，自动修复后仍无法解析："
                    f"line {repaired_error.lineno} column {repaired_error.colno}{suffix}"
                ) from original_error
        if not isinstance(payload, dict):
            raise ValueError("AI 返回格式错误")
        return SkillResult(
            content=raw, structured_output=payload, usage=response.usage,
            warnings=("json_syntax_repaired",) if repaired else (),
        )

    @staticmethod
    def _repair_common_json_syntax(raw: str) -> str:
        """Repair only deterministic, syntax-level JSON defects.

        Semantic values are never changed; Pydantic and evidence validation still
        run after this repair.
        """
        candidate = raw.replace("“", '"').replace("”", '"')
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        # Missing comma between a completed value and the next object field.
        candidate = re.sub(
            r'([}"\]\d])(?P<space>\s+)(?="[^"\r\n]+"\s*:)',
            r'\1,\g<space>',
            candidate,
        )
        # Missing comma between adjacent objects/arrays in an array.
        candidate = re.sub(r'([}\]])(?P<space>\s*)(?=[{\[])', r'\1,\g<space>', candidate)
        return candidate

    def validate_output(self, result: SkillResult, inputs: dict[str, Any]) -> None:
        payload = result.structured_output
        status = str(payload.get("normalized_status") or "")
        evidence = str(payload.get("raw_status") or "").strip()
        context = str(inputs["page_context"])
        if status != "unknown" and (not evidence or evidence.lower() not in context.lower()):
            raise ValueError("AI 给出的状态证据无法在页面原文中复核")
