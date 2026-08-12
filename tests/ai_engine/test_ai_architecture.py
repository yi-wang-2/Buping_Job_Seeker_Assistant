from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

# Existing legacy adapters remain temporarily allowlisted. New provider clients
# must be added to LLMGateway instead of expanding this set.
LEGACY_PROVIDER_FILES = {
    "src/libs/interview_prep/interview_generator.py",
    "src/libs/llm_manager.py",
    "src/libs/resume_and_cover_builder/llm/llm_generate_cover_letter_from_job.py",
    "src/libs/resume_and_cover_builder/llm/llm_generate_resume.py",
    "src/libs/resume_and_cover_builder/llm/llm_generate_resume_from_job.py",
    "src/libs/resume_and_cover_builder/llm/llm_job_parser.py",
    "src/libs/resume_and_cover_builder/utils.py",
}


def test_new_provider_construction_is_confined_to_gateway_or_legacy_allowlist():
    offenders: list[str] = []
    for base in (ROOT / "backend", ROOT / "src"):
        for path in base.rglob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            if relative == "src/libs/ai_engine/providers/gateway.py" or relative in LEGACY_PROVIDER_FILES:
                continue
            source = path.read_text(encoding="utf-8")
            if "from langchain_openai import ChatOpenAI" in source or "from langchain_anthropic import ChatAnthropic" in source:
                offenders.append(relative)
    assert offenders == [], f"Route new model construction through LLMGateway: {offenders}"
