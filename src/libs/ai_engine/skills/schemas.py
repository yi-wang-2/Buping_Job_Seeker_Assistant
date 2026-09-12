from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SkillInputModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class TextRewriterInput(SkillInputModel):
    text: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    target_language: Literal["zh", "en"] = "zh"
    context: str = ""


class ResumeReviewerInput(SkillInputModel):
    resume_text: str = Field(min_length=1)
    resume_blocks: list[dict[str, str]] = Field(default_factory=list)
    request: str = "请分析当前简历的优缺点"
    language: Literal["zh", "en"] = "zh"
    artifact_id: str = "resume.current"
    artifact_version: str = "unsaved"


class ResumeReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: str
    title: str
    analysis: str
    evidence_quote: str = Field(min_length=1)
    block_id: str = ""


class ResumeReviewPriority(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: Literal["high", "medium", "low"]
    action: str
    reason: str


class ResumeReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_summary: str = Field(min_length=1)
    strengths: list[ResumeReviewFinding] = Field(default_factory=list)
    weaknesses: list[ResumeReviewFinding] = Field(default_factory=list)
    priorities: list[ResumeReviewPriority] = Field(default_factory=list)
    grounding_status: Literal["grounded", "partially_grounded"] = "grounded"
    grounding_removed_count: int = Field(default=0, ge=0)


class JDAnalyzerInput(SkillInputModel):
    job_description: str = Field(min_length=1)
    source_url: str = ""


class JDAnalysis(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str | None = None
    company: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_years: int | float | str | None = None
    education: str | None = None
    location: str | None = None
    salary: str | None = None
    keywords: list[str] = Field(default_factory=list)


class ResumeWriterInput(SkillInputModel):
    resume: dict[str, Any]
    job_description: str = ""
    target_pages: Literal[1, 2] = 1
    regenerate_targets: list[str] = Field(default_factory=list)
    regeneration_context: str = ""
    language: Literal["zh", "en"] = "zh"
    operation: Literal["base_resume", "tailored_resume"] = "base_resume"


class InterviewCoachInput(SkillInputModel):
    resume: str = Field(min_length=1)
    job_description: str = Field(min_length=1)
    interview_type: str = "综合面试"
    question_count: int = Field(default=10, ge=1, le=50)
    language: Literal["zh", "en"] = "zh"
    prepared_prompt: str = ""
    knowledge_context: str = ""
    interview_blueprint: dict[str, Any] = Field(default_factory=dict)
    knowledge_source_ids: list[str] = Field(default_factory=list)
    knowledge_unit_ids: list[str] = Field(default_factory=list)
    selected_knowledge_source_ids: list[str] = Field(default_factory=list)


class MockInterviewerInput(SkillInputModel):
    prepared_prompt: str = ""
    resume: str = ""
    job_description: str = ""
    history: list[dict[str, Any]] = Field(default_factory=list)
    interview_type: str = "综合面试"
    selected_knowledge_source_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source(self) -> "MockInterviewerInput":
        if not self.prepared_prompt.strip() and not (self.resume.strip() and self.job_description.strip()):
            raise ValueError("Provide prepared_prompt or both resume and job_description")
        return self


class SkillMatcherInput(SkillInputModel):
    resume: str = Field(min_length=1)
    job_description: str = Field(min_length=1)


class SkillMatchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_score: float = Field(ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class CareerAdvisorInput(SkillInputModel):
    resume: str = Field(min_length=1)
    preferences: str = ""
    goals: str = ""
    history: str = ""


class CareerAdviceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    priorities: list[str] = Field(default_factory=list)
    action_plan: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class JobRecommenderInput(SkillInputModel):
    query: str = "请推荐最适合我的岗位"
    preferences: dict[str, Any] = Field(default_factory=dict)
    jobs: list[dict[str, Any]] = Field(min_length=1, max_length=50)
    limit: int = Field(default=10, ge=1, le=20)
    language: Literal["zh", "en"] = "zh"


class JobRecommendationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    fit_highlights: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


class JobRecommendationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    recommendations: list[JobRecommendationItem] = Field(default_factory=list)


class DirectChatInput(SkillInputModel):
    message: str = Field(min_length=1)
    page: str
    workspace_context: dict[str, Any] = Field(default_factory=dict)
    conversation_summary: str = ""
    language: Literal["zh", "en"] = "zh"


class JobStatusClassifierInput(SkillInputModel):
    page_context: str = Field(min_length=1)
    company: str = ""
    role: str = ""
    current_status: str = ""
    source_url: str = ""


class JobApplicationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    matched_target: bool = True
    normalized_status: Literal[
        "简历筛选", "笔试", "一面", "二面", "三面", "Offer", "泡池子", "简历挂", "unknown"
    ]
    raw_status: str
    confidence: float = Field(ge=0, le=1)
    application_match_confidence: float | None = Field(default=None, ge=0, le=1)
    status_confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str = ""


class JobStatusClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matched_application: bool
    normalized_status: Literal[
        "简历筛选", "笔试", "一面", "二面", "三面", "Offer", "泡池子", "简历挂", "unknown"
    ]
    raw_status: str
    confidence: float = Field(ge=0, le=1)
    application_match_confidence: float | None = Field(default=None, ge=0, le=1)
    status_confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str = ""
    applications: list[JobApplicationStatus] = Field(default_factory=list)
