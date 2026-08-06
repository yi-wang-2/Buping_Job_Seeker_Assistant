"""Runtime guardrails for AI-generated content."""

from .resume_facts import EducationGuardResult, protect_education_section

__all__ = ["EducationGuardResult", "protect_education_section"]
