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


class JDAnalyzerInput(SkillInputModel):
    job_description: str = Field(min_length=1)


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
    resume: str = ""
    job_description: str = ""
    language: Literal["zh", "en"] = "zh"
    template: str = ""
    prepared_prompt: str = ""

    @model_validator(mode="after")
    def validate_source(self) -> "ResumeWriterInput":
        if not self.prepared_prompt.strip() and not self.resume.strip():
            raise ValueError("Provide prepared_prompt or resume")
        return self


class InterviewCoachInput(SkillInputModel):
    resume: str = Field(min_length=1)
    job_description: str = Field(min_length=1)
    interview_type: str = "综合面试"
    question_count: int = Field(default=10, ge=1, le=50)
    language: Literal["zh", "en"] = "zh"
    prepared_prompt: str = ""


class MockInterviewerInput(SkillInputModel):
    prepared_prompt: str = ""
    resume: str = ""
    job_description: str = ""
    history: list[dict[str, Any]] = Field(default_factory=list)

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
        "简历筛选", "笔试", "技术面", "主管面", "HR面", "Offer", "泡池子", "简历挂", "unknown"
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
        "简历筛选", "笔试", "技术面", "主管面", "HR面", "Offer", "泡池子", "简历挂", "unknown"
    ]
    raw_status: str
    confidence: float = Field(ge=0, le=1)
    application_match_confidence: float | None = Field(default=None, ge=0, le=1)
    status_confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str = ""
    applications: list[JobApplicationStatus] = Field(default_factory=list)
