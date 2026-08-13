"""JD-tailored resume generation using the shared resume_writer Skill."""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from src.libs.resume_and_cover_builder.llm.llm_generate_resume import LLMResumer


class LLMResumeJobDescription(LLMResumer):
    """Adds JD summarization; generation itself is inherited and unified."""

    def set_job_description_from_text(self, job_description_text: str) -> None:
        self._report_progress(28, "jd_summary", "Summarizing the job description")
        prompt = ChatPromptTemplate.from_template(self.strings.summarize_prompt_template)
        messages = prompt.format_messages(text=job_description_text)
        response = self.gateway_chat.invoke(
            messages,
            trace_metadata={"operation": "summarize_job_description"},
        )
        self.job_description = response.content.strip()
        self._report_progress(29, "jd_summary", "Job description summary completed")
