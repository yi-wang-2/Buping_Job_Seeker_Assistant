"""Runtime guardrails for AI-generated resume content."""

from .resume_facts import (
    FACT_POLICY,
    EducationGuardResult,
    FactPolicy,
    GuardViolation,
    ResumeGuardResult,
    policy_for,
    protect_education_section,
    protect_resume_sections,
    validate_grounded_text,
)
from .resume_typography import (
    TypographyAdjustment,
    TypographyHarnessResult,
    enforce_resume_typography,
)
from .resume_quality import (
    GOLDEN_RESUME_WRITING_GUIDE,
    CandidateEvaluation,
    HardFactResult,
    evaluate_resume_candidate,
    generate_candidates,
    protect_hard_facts_in_place,
    select_best_candidate,
)

__all__ = [
    "FACT_POLICY", "EducationGuardResult", "FactPolicy", "GuardViolation",
    "ResumeGuardResult", "policy_for", "protect_education_section",
    "protect_resume_sections", "validate_grounded_text",
    "TypographyAdjustment", "TypographyHarnessResult", "enforce_resume_typography",
    "GOLDEN_RESUME_WRITING_GUIDE", "CandidateEvaluation", "HardFactResult",
    "evaluate_resume_candidate", "generate_candidates", "protect_hard_facts_in_place",
    "select_best_candidate",
]
