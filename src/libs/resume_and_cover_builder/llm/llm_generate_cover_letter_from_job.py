"""
This creates the cover letter (in html, utils will then convert in PDF) matching with job description and plain-text resume
"""
# app/libs/resume_and_cover_builder/llm_generate_cover_letter_from_job.py
import os
import textwrap
from ..utils import LoggerChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
import config as cfg

try:
    if cfg.LLM_MODEL_TYPE == 'anthropic':
        from langchain_anthropic import ChatAnthropic as ChatModel
    else:
        from langchain_openai import ChatOpenAI as ChatModel
except Exception:
    from langchain_openai import ChatOpenAI as ChatModel


def _create_chat_model(api_key: str):
    if cfg.LLM_MODEL_TYPE == 'anthropic':
        model_name = cfg.ANTHROPIC_MODEL or cfg.LLM_MODEL or ""
        base_url = cfg.ANTHROPIC_BASE_URL or ""
        try:
            if base_url:
                return ChatModel(model=model_name, api_key=api_key, base_url=base_url, temperature=0.4)
            return ChatModel(model=model_name, api_key=api_key, temperature=0.4)
        except TypeError:
            try:
                if base_url:
                    return ChatModel(model=model_name, api_key=api_key, anthropic_api_url=base_url, temperature=0.4)
                return ChatModel(model=model_name, api_key=api_key, temperature=0.4)
            except TypeError:
                return ChatModel(model=model_name, api_key=api_key, temperature=0.4)

    model_name = cfg.LLM_MODEL or "gpt-4o-mini"
    base_url = cfg.LLM_API_URL or ""
    if base_url:
        return ChatModel(model_name=model_name, openai_api_key=api_key, base_url=base_url, temperature=0.4)
    return ChatModel(model_name=model_name, openai_api_key=api_key, temperature=0.4)
from langchain_openai import OpenAIEmbeddings
from pathlib import Path
from dotenv import load_dotenv
from requests.exceptions import HTTPError as HTTPStatusError
from pathlib import Path
from loguru import logger

# Load environment variables from .env file
load_dotenv()

# Configure log file
log_folder = 'log/cover_letter/gpt_cover_letter_job_descr'
if not os.path.exists(log_folder):
    os.makedirs(log_folder)
log_path = Path(log_folder).resolve()
logger.add(log_path / "gpt_cover_letter_job_descr.log", rotation="1 day", compression="zip", retention="7 days", level="DEBUG")

class LLMCoverLetterJobDescription:
    def __init__(self, openai_api_key, strings):
        api_key = cfg.ANTHROPIC_AUTH_TOKEN or openai_api_key
        llm_client = _create_chat_model(api_key)
        self.llm_cheap = LoggerChatModel(llm_client)
        self.llm_embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
        self.strings = strings

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
        Set the resume text to be used for generating the cover letter.
        Args:
            resume (str): The plain text resume to be used.
        """
        self.resume = resume

    def set_job_description_from_text(self, job_description_text) -> None:
        """
        Set the job description text to be used for generating the cover letter.
        Args:
            job_description_text (str): The plain text job description to be used.
        """
        logger.debug("Starting job description summarization...")
        prompt = ChatPromptTemplate.from_template(self.strings.summarize_prompt_template)
        chain = prompt | self.llm_cheap | StrOutputParser()
        output = chain.invoke({"text": job_description_text})
        self.job_description = output
        logger.debug(f"Job description summarization complete: {self.job_description}")

    def generate_cover_letter(self) -> str:
        """
        Generate the cover letter based on the job description and resume.
        Returns:
            str: The generated cover letter
        """
        logger.debug("Starting cover letter generation...")
        prompt_template = self._preprocess_template_string(self.strings.cover_letter_template)
        logger.debug(f"Cover letter template after preprocessing: {prompt_template}")

        prompt = ChatPromptTemplate.from_template(prompt_template)
        logger.debug(f"Prompt created: {prompt}")

        chain = prompt | self.llm_cheap | StrOutputParser()
        logger.debug(f"Chain created: {chain}")

        input_data = {
            "job_description": self.job_description,
            "resume": self.resume
        }
        logger.debug(f"Input data: {input_data}")

        output = chain.invoke(input_data)
        logger.debug(f"Cover letter generation result: {output}")

        logger.debug("Cover letter generation completed")
        return output
