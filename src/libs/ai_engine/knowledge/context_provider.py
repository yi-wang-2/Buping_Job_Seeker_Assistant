from __future__ import annotations

from dataclasses import dataclass
import json

from ..context import ContextItem, ContextKind, ContextProviderResult
from .models import InterviewBlueprint, KnowledgeQuery, RetrievalResult
from .retrieval import HybridKnowledgeRetriever


COMPETENCIES = {
    "language": ("java", "python", "c++", "javascript", "typescript", "编程语言"),
    "data": ("sql", "mysql", "redis", "数据库", "缓存"),
    "ai": ("llm", "rag", "agent", "大模型", "机器学习", "深度学习"),
    "system_design": ("架构", "分布式", "高并发", "系统设计", "微服务"),
    "delivery": ("项目", "上线", "性能", "可靠性", "测试", "运维"),
    "behavioral": ("沟通", "协作", "领导", "冲突", "复盘"),
}


@dataclass(frozen=True)
class KnowledgeAugmentation:
    blueprint: InterviewBlueprint
    retrieval: RetrievalResult | None
    context: str
    warnings: tuple[str, ...] = ()


class InterviewKnowledgeContextProvider:
    def __init__(self, retriever: HybridKnowledgeRetriever, *, max_characters: int = 8000) -> None:
        self.retriever = retriever
        self.max_characters = max(1000, max_characters)

    @staticmethod
    def build_blueprint(resume: str, job_description: str, interview_type: str) -> InterviewBlueprint:
        jd_text = job_description.casefold()
        resume_text = resume.casefold()
        target_role = next((line.strip() for line in job_description.splitlines() if line.strip()), "")[:120]
        required = {
            name: [term for term in terms if term.casefold() in jd_text]
            for name, terms in COMPETENCIES.items()
        }
        required = {name: values for name, values in required.items() if values}
        if not required:
            combined = f"{job_description}\n{resume}".casefold()
            required = {
                name: [term for term in terms if term.casefold() in combined]
                for name, terms in COMPETENCIES.items()
            }
            required = {name: values for name, values in required.items() if values}
        if not required:
            required = {"role_fundamentals": [target_role or "岗位基础"]}
        raw_weights = {
            name: max(1, sum(jd_text.count(term.casefold()) for term in values))
            for name, values in required.items()
        }
        denominator = sum(raw_weights.values())
        weights = {name: round(value / denominator, 4) for name, value in raw_weights.items()}
        first = next(iter(weights))
        weights[first] = round(weights[first] + (1 - sum(weights.values())), 4)
        evidence: dict[str, list[str]] = {}
        for name, terms in required.items():
            evidence[name] = [
                line.strip()[:300] for line in resume.splitlines()
                if line.strip() and any(term.casefold() in line.casefold() for term in terms)
            ][:3]
        gaps = [name for name, lines in evidence.items() if not lines]
        technical = interview_type not in {"行为面试", "HR面试"}
        return InterviewBlueprint(
            target_role=target_role,
            competency_weights=weights,
            evidence_by_competency=evidence,
            gaps=gaps,
            question_mix={"technical": .7, "project": .2, "behavioral": .1} if technical else {
                "technical": .1, "project": .3, "behavioral": .6,
            },
            difficulty_path=["introductory", "intermediate", "advanced"],
            weak_topics=gaps or list(required),
        )

    def prepare(
        self, *, resume: str, job_description: str, interview_type: str,
        user_id: str = "local", session_id: str | None = None,
        source_ids: list[str] | None = None,
    ) -> KnowledgeAugmentation:
        blueprint = self.build_blueprint(resume, job_description, interview_type)
        topics = [*blueprint.competency_weights, *blueprint.weak_topics][:20]
        scopes = ["public", "user"] + (["session"] if session_id else [])
        try:
            retrieval = self.retriever.retrieve(KnowledgeQuery(
                text=f"{blueprint.target_role} {interview_type} {' '.join(topics)}",
                domain=None,
                roles=[], topics=[],
                scopes=scopes, user_id=user_id, session_id=session_id, top_k=8,
                source_ids=list(source_ids or []),
            ))
        except Exception as exc:
            return KnowledgeAugmentation(
                blueprint=blueprint, retrieval=None, context="",
                warnings=(f"knowledge retrieval unavailable: {type(exc).__name__}",),
            )
        if not retrieval.hits:
            return KnowledgeAugmentation(
                blueprint=blueprint, retrieval=retrieval, context="",
                warnings=tuple([*retrieval.warnings, "no relevant knowledge found"]),
            )
        blocks = []
        source_ids = []
        used = 0
        for hit in retrieval.hits:
            unit = hit.unit
            block = (
                f"[K:{unit.id}] {unit.title}\n"
                f"来源：{unit.source_id} / {unit.source_path}\n"
                f"类型：{unit.unit_type}；主题：{unit.topic or '未标注'}\n"
                f"{unit.content}\n"
            )
            remaining = self.max_characters - used
            if remaining <= 0:
                break
            blocks.append(block[:remaining])
            used += len(block[:remaining])
            source_ids.append(unit.source_id)
        blueprint = blueprint.model_copy(update={"source_ids": list(dict.fromkeys(source_ids))})
        instruction = (
            "以下内容是外部面试知识，不是候选人的经历或事实。仅用于补充问题和评价标准；"
            "采用其中知识时必须保留 [K:知识单元ID] 引用。知识不足时明确说明，不得编造来源。\n\n"
        )
        return KnowledgeAugmentation(
            blueprint=blueprint, retrieval=retrieval, context=instruction + "\n".join(blocks),
            warnings=tuple(retrieval.warnings),
        )


class InterviewKnowledgeRuntimeProvider:
    """Adapt interview retrieval to the Runtime pre-context provider contract."""

    name = "interview_knowledge"

    def __init__(self, retriever: HybridKnowledgeRetriever, *, max_characters: int = 8000) -> None:
        self.provider = InterviewKnowledgeContextProvider(retriever, max_characters=max_characters)

    def provide(
        self, *, skill_name: str, inputs: dict, user_id: str, session_id: str | None,
    ) -> ContextProviderResult:
        if skill_name not in {"interview_coach", "mock_interviewer"}:
            return ContextProviderResult()
        resume = str(inputs.get("resume") or "").strip()
        job_description = str(inputs.get("job_description") or "").strip()
        if not resume or not job_description:
            return ContextProviderResult(warnings=("Interview knowledge skipped: resume or JD is missing",))
        augmentation = self.provider.prepare(
            resume=resume, job_description=job_description,
            interview_type=str(inputs.get("interview_type") or "综合面试"),
            user_id=user_id, session_id=session_id,
            source_ids=list(inputs.get("selected_knowledge_source_ids") or []),
        )
        unit_ids = [hit.unit.id for hit in augmentation.retrieval.hits] if augmentation.retrieval else []
        items = [ContextItem(
            "interview-knowledge-blueprint", ContextKind.WORKING,
            json.dumps(augmentation.blueprint.model_dump(mode="json"), ensure_ascii=False),
            "interview_blueprint", priority=92, relevance=.95,
        )]
        if augmentation.context:
            items.append(ContextItem(
                "interview-retrieved-knowledge", ContextKind.RETRIEVED,
                augmentation.context, "knowledge_retrieval", priority=88, relevance=.9,
                metadata={"untrusted": True, "source_ids": augmentation.blueprint.source_ids},
            ))
        retrieval = augmentation.retrieval
        metadata = {
            "knowledge_source_ids": augmentation.blueprint.source_ids,
            "knowledge_unit_ids": unit_ids,
            "knowledge_index_version": retrieval.index_version if retrieval else "",
            "knowledge_retrieval_ms": retrieval.retrieval_ms if retrieval else 0,
            "knowledge_candidates": retrieval.total_candidates if retrieval else 0,
        }
        return ContextProviderResult(
            items=tuple(items),
            input_updates={
                "interview_blueprint": augmentation.blueprint.model_dump(mode="json"),
                "knowledge_source_ids": augmentation.blueprint.source_ids,
                "knowledge_unit_ids": unit_ids,
            },
            metadata=metadata, warnings=augmentation.warnings,
        )
