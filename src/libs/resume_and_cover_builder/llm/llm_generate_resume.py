"""
Create a class that generates a resume based on a resume and a resume template.
"""
# app/libs/resume_and_cover_builder/gpt_resume.py
import os
import textwrap
from typing import Any
import config as cfg
from src.libs.ai_engine.harness import (
    evaluate_resume_candidate,
    generate_candidates,
    protect_hard_facts_in_place,
    select_best_candidate,
)


# choose model client dynamically based on LLM_PROTOCOL
# LLM_PROTOCOL is the wire protocol (independent of provider):
#   - "anthropic"        → Anthropic Messages API (ChatAnthropic)
#   - "openai_chat"      → OpenAI Chat Completions API (ChatOpenAI)
#   - "openai_response"  → OpenAI Responses API (ChatOpenAI with Responses path)
# LLM_MODEL_TYPE is the provider (anthropic/openai/deepseek/zhipu/...) — kept
# for backward compatibility and as a label in the UI.
def _resolve_protocol() -> str:
    """Resolve LLM protocol with backward compatibility."""
    proto = getattr(cfg, "LLM_PROTOCOL", None)
    if proto:
        return str(proto).lower()
    # Fallback: derive from LLM_MODEL_TYPE (legacy behavior)
    if cfg.LLM_MODEL_TYPE == "anthropic":
        return "anthropic"
    return "openai_chat"


def _strip_base_url_path(base_url: str, proto: str = "openai_chat") -> str:
    """Normalize base URLs without dropping required provider path prefixes.

    langchain ChatOpenAI appends "/chat/completions" (or "/responses" for
    the Responses API) to whatever base_url you give it. If a user pastes
    a full URL like "https://api.minimaxi.com/anthropic/v1/messages",
    the request would hit
    ".../anthropic/v1/messages/chat/completions" and get 404.

    This helper keeps only the scheme + host, discarding any path or
    query string. For example:
        "https://api.minimaxi.com"                   → "https://api.minimaxi.com"
        "https://api.minimaxi.com/"                  → "https://api.minimaxi.com"
        "https://api.minimaxi.com/v1"                → "https://api.minimaxi.com"
        "https://api.minimaxi.com/anthropic/v1/messages" → "https://api.minimaxi.com"
    """
    if not base_url:
        return base_url
    from urllib.parse import urlparse, urlunparse

    try:
        parsed = urlparse(base_url)
        path = (parsed.path or "").rstrip("/")

        if proto == "anthropic":
            if path.endswith("/v1/messages"):
                path = path[: -len("/v1/messages")]
            elif path.endswith("/messages"):
                path = path[: -len("/messages")]
        else:
            for suffix in ("/chat/completions", "/completions", "/responses"):
                if path.endswith(suffix):
                    path = path[: -len(suffix)]
                    break

        return urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")).rstrip("/")
    except Exception:
        return base_url.rstrip("/")


def _create_chat_model(api_key: str):
    proto = _resolve_protocol()

    if proto == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic as ChatModel
        except Exception:
            from langchain_openai import ChatOpenAI as ChatModel
        # Anthropic Messages API (also used by Anthropic-compatible providers
        # such as MiniMax when configured to expose /anthropic endpoint)
        model_name = cfg.ANTHROPIC_MODEL or cfg.LLM_MODEL or ""
        base_url = cfg.ANTHROPIC_BASE_URL or ""
        try:
            if base_url:
                return ChatModel(model=model_name, api_key=api_key, base_url=base_url, temperature=0.4, max_tokens=4096)
            return ChatModel(model=model_name, api_key=api_key, temperature=0.4, max_tokens=4096)
        except TypeError:
            try:
                if base_url:
                    return ChatModel(model=model_name, api_key=api_key, anthropic_api_url=base_url, temperature=0.4, max_tokens=4096)
                return ChatModel(model=model_name, api_key=api_key, temperature=0.4, max_tokens=4096)
            except TypeError:
                return ChatModel(model=model_name, api_key=api_key, temperature=0.4, max_tokens=4096)

    # OpenAI Chat Completions (default for openai_chat) OR Responses API
    # We currently use ChatOpenAI for both; the protocol is recorded so the
    # frontend/UI can display it correctly. To call the Responses API
    # specifically, langchain-openai >= 0.3 supports `output_version`
    # ("responses_v1") — see OpenAI provider docs.
    from langchain_openai import ChatOpenAI as ChatModel
    model_name = (
        cfg.OPENAI_MODEL
        if proto == "openai_response" and getattr(cfg, "OPENAI_MODEL", None)
        else (cfg.LLM_MODEL or "gpt-4o-mini")
    )
    raw_base_url = getattr(cfg, "OPENAI_BASE_URL", None) or cfg.LLM_API_URL or ""

    # IMPORTANT: langchain ChatOpenAI appends "/chat/completions" (or
    # "/responses" for output_version=responses_v1) to whatever base_url
    # you give it. So if a user pastes a full URL like
    # "https://api.minimaxi.com/anthropic/v1/messages" we MUST strip the
    # path — otherwise the request hits
    # ".../anthropic/v1/messages/chat/completions" and gets 404.
    base_url = _strip_base_url_path(raw_base_url, proto=proto)

    # Detect Responses API support
    use_responses = proto == "openai_response"

    if base_url:
        try:
            kwargs = {
                "model_name": model_name,
                "openai_api_key": api_key,
                "base_url": base_url,
                "temperature": 0.4,
                "max_tokens": 4096,
            }
            if use_responses:
                # langchain-openai >= 0.3: opt into Responses API
                kwargs["output_version"] = "responses_v1"
            return ChatModel(**kwargs)
        except TypeError:
            # Older langchain-openai: try without output_version
            kwargs.pop("output_version", None)
            return ChatModel(model_name=model_name, openai_api_key=api_key, base_url=base_url, temperature=0.4)
    try:
        return ChatModel(model_name=model_name, openai_api_key=api_key, temperature=0.4, max_tokens=4096)
    except TypeError:
        return ChatModel(model_name=model_name, openai_api_key=api_key, temperature=0.4)


def _create_gateway_chat_model(api_key: str, *, skill: str, max_output_tokens: int = 4096):
    """Build the common Gateway adapter for incrementally migrated resume calls."""
    from src.libs.ai_engine.observability import JsonlTraceSink
    from src.libs.ai_engine.observability.langchain_tracing import GatewayChatClient
    from src.libs.ai_engine.providers import GatewayConfig, LLMGateway

    protocol = _resolve_protocol()
    provider = "anthropic" if protocol == "anthropic" else "openai"
    if protocol == "anthropic":
        model = cfg.ANTHROPIC_MODEL or cfg.LLM_MODEL or "MiniMax-M3"
        base_url = cfg.ANTHROPIC_BASE_URL or ""
    else:
        model = cfg.LLM_MODEL or getattr(cfg, "OPENAI_MODEL", "") or "gpt-4o-mini"
        raw_base_url = getattr(cfg, "OPENAI_BASE_URL", None) or cfg.LLM_API_URL or ""
        base_url = _strip_base_url_path(raw_base_url, proto=protocol)
    gateway = LLMGateway(
        GatewayConfig(api_key=api_key, base_url=base_url, max_retries=2),
        trace_sink=JsonlTraceSink(),
    )
    return GatewayChatClient(
        gateway, provider=provider, model=model, skill=skill,
        temperature=0.4, max_output_tokens=max_output_tokens,
    )


def _create_resume_runtime(api_key: str):
    """Create the structured resume_writer runtime without a chat compatibility adapter."""
    from backend.services.ai_runtime_service import build_ai_runtime
    from src.libs.ai_engine.skills.builtin import ResumeWriterSkill

    protocol = _resolve_protocol()
    provider = "anthropic" if protocol == "anthropic" else "openai"
    if protocol == "anthropic":
        model = cfg.ANTHROPIC_MODEL or cfg.LLM_MODEL or "MiniMax-M3"
        base_url = cfg.ANTHROPIC_BASE_URL or ""
    else:
        model = cfg.LLM_MODEL or getattr(cfg, "OPENAI_MODEL", "") or "gpt-4o-mini"
        raw_base_url = getattr(cfg, "OPENAI_BASE_URL", None) or cfg.LLM_API_URL or ""
        base_url = _strip_base_url_path(raw_base_url, proto=protocol)
    bundle = build_ai_runtime(
        {"api_key": api_key, "base_url": base_url, "provider": provider, "model": model},
        [ResumeWriterSkill()],
    )
    return bundle.runtime, provider, model
from dotenv import load_dotenv
from loguru import logger
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

# Configure log file
log_folder = 'log/resume/gpt_resume'
if not os.path.exists(log_folder):
    os.makedirs(log_folder)
log_path = Path(log_folder).resolve()
logger.add(log_path / "gpt_resume.log", rotation="1 day", compression="zip", retention="7 days", level="DEBUG")

class LLMResumer:
    def __init__(self, openai_api_key, strings):
        api_key = openai_api_key or cfg.ANTHROPIC_AUTH_TOKEN
        self.resume_runtime, self.resume_provider, self.resume_model = _create_resume_runtime(api_key)
        # JD summarization is a separate support call and does not enter the
        # resume_writer generation contract.
        self.gateway_chat = _create_gateway_chat_model(api_key, skill="resume_support")
        self.strings = strings
        self.regeneration_context_html = ""
        self.regenerate_targets: list[str] = []
        self.target_pages = 1
        self.progress_callback = None

    @staticmethod
    def _preprocess_template_string(template: str) -> str:
        """
        Preprocess the template string by removing leading whitespace and indentation.
        Args:
            template (str): The template string to preprocess.
        Returns:
            str: The preprocessed template string.
        """
        return textwrap.dedent(template)

    def set_resume(self, resume) -> None:
        """
        Set the resume object to be used for generating the resume.
        Args:
            resume (Resume): The resume object to be used.
        """
        self.resume = resume

    def set_regeneration_context(self, context_html: str, targets: list[str] | None = None) -> None:
        """Provide locked content and formatting as reference for partial regeneration."""

        self.regeneration_context_html = context_html or ""
        self.regenerate_targets = list(targets or [])

    def set_target_pages(self, target_pages: int) -> None:
        self.target_pages = target_pages if target_pages in {1, 2} else 1

    def set_progress_callback(self, callback) -> None:
        self.progress_callback = callback

    def _report_progress(self, progress: int, stage: str, detail: str = "") -> None:
        callback = getattr(self, "progress_callback", None)
        if callback:
            callback(progress, stage, detail)

    def _invoke_resume_skill(self, input_data: dict) -> str:
        return self.resume_runtime.execute(
            "resume_writer", input_data,
            provider=self.resume_provider, model=self.resume_model,
        ).content

    def _generate_best_sections(self, input_data: dict, *, operation: str) -> dict[str, str]:
        """Generate multiple candidates, score them locally, then protect hard facts."""
        self._report_progress(30, "llm_candidates", "Started parallel candidate generation")

        def candidate_finished(completed: int, total: int, success: bool) -> None:
            progress = 30 + round(24 * completed / total)
            outcome = "completed" if success else "failed"
            self._report_progress(
                progress,
                "llm_candidates",
                f"Candidate {completed}/{total} {outcome}",
            )

        outputs = generate_candidates(
            lambda: self._invoke_resume_skill(input_data),
            on_complete=candidate_finished,
        )
        candidates = [self._parse_unified_output(output) for output in outputs]
        candidates = [candidate for candidate in candidates if candidate]
        if not candidates:
            raise RuntimeError("The model returned no parseable resume candidate")
        self._report_progress(57, "candidate_parsing", f"Parsed {len(candidates)} candidate(s)")

        evaluations = [evaluate_resume_candidate(candidate, self.resume) for candidate in candidates]
        selected = select_best_candidate(candidates, self.resume)
        self._report_progress(61, "candidate_scoring", "Scored candidates and selected the best version")
        logger.info(
            "Resume candidate selection operation={} scores={} selected_score={} breakdown={}",
            operation,
            [evaluation.score for evaluation in evaluations],
            selected.score,
            selected.breakdown,
        )
        if selected.project_structure_issues:
            logger.warning(
                "Selected resume candidate has incomplete project structure: {}",
                selected.project_structure_issues,
            )
        protected = protect_hard_facts_in_place(
            selected.sections,
            self.resume,
            language="en" if getattr(cfg, "RESUME_LANGUAGE", "zh") == "en" else "zh",
        )
        self._report_progress(65, "hard_fact_guard", "Verified and corrected hard facts")
        if protected.violations:
            logger.warning(
                "Resume hard-fact guard corrected {} claims: {}",
                len(protected.violations),
                protected.violations,
            )
        return protected.sections

    def _resume_payload(self) -> dict:
        if isinstance(self.resume, dict):
            return self.resume
        dump = getattr(self.resume, "model_dump", None)
        if not callable(dump):
            raise TypeError("Resume object must support model_dump()")
        return dump(mode="json")

    def generate_all_sections(self) -> dict:
        """Send structured facts to resume_writer; the Skill owns prompt assembly."""
        logger.debug("Starting unified structured resume generation")
        input_data = {
            "resume": self._resume_payload(),
            "job_description": str(getattr(self, "job_description", "") or ""),
            "target_pages": self.target_pages,
            "regenerate_targets": self.regenerate_targets,
            "regeneration_context": self.regeneration_context_html,
            "language": "en" if getattr(cfg, "RESUME_LANGUAGE", "zh") == "en" else "zh",
            "operation": "tailored_resume" if getattr(self, "job_description", "") else "base_resume",
        }
        sections = self._generate_best_sections(
            input_data, operation=input_data["operation"],
        )
        logger.debug(f"Parsed sections: {list(sections.keys())}")
        return sections

    def _parse_unified_output(self, output: str) -> dict:
        """
        Parse the unified LLM output into individual sections.
        
        Args:
            output: The raw output string containing marked sections.
            
        Returns:
            dict: A dictionary mapping section names to their HTML content.
        """
        import re
        sections = {}
        
        # Define section markers with start and end patterns
        section_markers = [
            (r'\[HEADER\]', r'\[/HEADER\]', 'header'),
            (r'\[SUMMARY\]', r'\[/SUMMARY\]', 'summary'),
            (r'\[EDUCATION\]', r'\[/EDUCATION\]', 'education'),
            (r'\[WORK_EXPERIENCE\]', r'\[/WORK_EXPERIENCE\]', 'work_experience'),
            (r'\[PROJECTS\]', r'\[/PROJECTS\]', 'projects'),
            (r'\[ACADEMIC_ACHIEVEMENTS\]', r'\[/ACADEMIC_ACHIEVEMENTS\]', 'academic_achievements'),
            (r'\[ACHIEVEMENTS\]', r'\[/ACHIEVEMENTS\]', 'achievements'),
            (r'\[CERTIFICATIONS\]', r'\[/CERTIFICATIONS\]', 'certifications'),
            (r'\[ADDITIONAL_SKILLS\]', r'\[/ADDITIONAL_SKILLS\]', 'additional_skills'),
        ]
        
        for start_marker, end_marker, key in section_markers:
            # Find content between start and end markers
            pattern = rf'{start_marker}(.*?){end_marker}'
            match = re.search(pattern, output, re.DOTALL | re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                if content:
                    sections[key] = content
        
        return sections

    def generate_html_resume(self) -> str:
        """
        Generate the full HTML resume based on the resume object.
        Uses a single LLM call to generate all sections for better coherence.
        Returns:
            str: The generated HTML resume.
        """
        logger.debug("Starting unified resume generation (single LLM call)")
        
        # Generate all sections in a single LLM call
        results = self.generate_all_sections()
        
        # Assemble a body fragment. ResumeGenerator owns the document template;
        # returning another <body> here creates nested documents after rendering.
        full_resume = f"  {results.get('header', '')}\n"
        full_resume += "  <main>\n"
        full_resume += f"    {results.get('summary', '')}\n"
        full_resume += f"    {results.get('education', '')}\n"
        full_resume += f"    {results.get('work_experience', '')}\n"
        full_resume += f"    {results.get('projects', '')}\n"
        full_resume += f"    {results.get('academic_achievements', '')}\n"
        full_resume += f"    {results.get('achievements', '')}\n"
        full_resume += f"    {results.get('certifications', '')}\n"
        full_resume += f"    {results.get('additional_skills', '')}\n"
        full_resume += "  </main>\n"
        
        logger.debug("Unified resume generation completed")
        return full_resume
