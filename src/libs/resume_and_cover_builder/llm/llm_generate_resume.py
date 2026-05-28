"""
Create a class that generates a resume based on a resume and a resume template.
"""
# app/libs/resume_and_cover_builder/gpt_resume.py
import os
import textwrap
from typing import Any
from src.libs.resume_and_cover_builder.utils import LoggerChatModel
from langchain_core.output_parsers import BaseOutputParser
from langchain_core.prompts import ChatPromptTemplate
import config as cfg


class ContentBlockParser(BaseOutputParser):
    """
    Custom parser to extract only 'text' blocks from content blocks returned by the API.
    This prevents 'thinking' blocks and prompt text from being included in the output.
    """
    def parse(self, result: Any) -> str:
        """
        Parse the result, extracting only text blocks.
        
        Args:
            result: Can be a list of content blocks (e.g., [{'type': 'thinking', ...}, {'type': 'text', ...}])
                   or a string, or an AIMessage object.
        
        Returns:
            str: The extracted text content only, or original string if not a list.
        """
        # If it's an AIMessage or has content attribute, extract content
        if hasattr(result, 'content'):
            result = result.content
        
        # If it's a list of content blocks, extract only 'text' blocks
        if isinstance(result, list):
            text_parts = []
            for block in result:
                if isinstance(block, dict):
                    if block.get('type') == 'text':
                        text_parts.append(block.get('text', ''))
                    # Skip 'thinking' blocks to avoid prompt leakage
            return ''.join(text_parts)
        
        # Otherwise return as string
        return str(result) if result else ''
    
    @property
    def _type(self) -> str:
        return 'content_block_parser'

# choose model client dynamically
try:
    if cfg.LLM_MODEL_TYPE == 'anthropic':
        from langchain_anthropic import ChatAnthropic as ChatModel
    else:
        from langchain_openai import ChatOpenAI as ChatModel
except Exception:
    # fallback to OpenAI Chat if imports fail
    from langchain_openai import ChatOpenAI as ChatModel


def _create_chat_model(api_key: str):
    if cfg.LLM_MODEL_TYPE == 'anthropic':
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

    model_name = cfg.LLM_MODEL or "gpt-4o-mini"
    base_url = cfg.LLM_API_URL or ""
    if base_url:
        return ChatModel(model_name=model_name, openai_api_key=api_key, base_url=base_url, temperature=0.4, max_tokens=4096)
    return ChatModel(model_name=model_name, openai_api_key=api_key, temperature=0.4, max_tokens=4096)
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        # instantiate appropriate chat model
        api_key = cfg.ANTHROPIC_AUTH_TOKEN or openai_api_key
        llm_client = _create_chat_model(api_key)
        self.llm_cheap = LoggerChatModel(llm_client)
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
        Set the resume object to be used for generating the resume.
        Args:
            resume (Resume): The resume object to be used.
        """
        self.resume = resume

    def generate_header(self, data = None) -> str:
        """
        Generate the header section of the resume.
        Args:
            data (dict): The personal information to use for generating the header.
        Returns:
            str: The generated header section.
        """
        header_prompt_template = self._preprocess_template_string(
            self.strings.prompt_header
        )
        prompt = ChatPromptTemplate.from_template(header_prompt_template)
        chain = prompt | self.llm_cheap | ContentBlockParser()
        input_data = {
            "personal_information": self.resume.personal_information
        } if data is None else data
        output = chain.invoke(input_data)
        return output
    
    def generate_education_section(self, data = None) -> str:
        """
        Generate the education section of the resume.
        Args:
            data (dict): The education details to use for generating the education section.
        Returns:
            str: The generated education section.
        """
        logger.debug("Starting education section generation")

        education_prompt_template = self._preprocess_template_string(self.strings.prompt_education)
        logger.debug(f"Education template: {education_prompt_template}")

        prompt = ChatPromptTemplate.from_template(education_prompt_template)
        logger.debug(f"Prompt: {prompt}")
        
        chain = prompt | self.llm_cheap | ContentBlockParser()
        logger.debug(f"Chain created: {chain}")
        
        input_data = {
            "education_details": self.resume.education_details
        } if data is None else data
        output = chain.invoke(input_data)
        logger.debug(f"Chain invocation result: {output}")

        logger.debug("Education section generation completed")
        return output

    def generate_work_experience_section(self, data = None) -> str:
        """
        Generate the work experience section of the resume.
        Args:
            data (dict): The work experience details to use for generating the work experience section.
        Returns:
            str: The generated work experience section.
        """
        logger.debug("Starting work experience section generation")

        work_experience_prompt_template = self._preprocess_template_string(self.strings.prompt_working_experience)
        logger.debug(f"Work experience template: {work_experience_prompt_template}")

        prompt = ChatPromptTemplate.from_template(work_experience_prompt_template)
        logger.debug(f"Prompt: {prompt}")
        
        chain = prompt | self.llm_cheap | ContentBlockParser()
        logger.debug(f"Chain created: {chain}")
        
        input_data = {
            "experience_details": self.resume.experience_details
        } if data is None else data
        output = chain.invoke(input_data)
        logger.debug(f"Chain invocation result: {output}")

        logger.debug("Work experience section generation completed")
        return output

    def generate_projects_section(self, data = None) -> str:
        """
        Generate the side projects section of the resume.
        Args:
            data (dict): The side projects to use for generating the side projects section.
        Returns:
            str: The generated side projects section.
        """
        logger.debug("Starting side projects section generation")

        projects_prompt_template = self._preprocess_template_string(self.strings.prompt_projects)
        logger.debug(f"Side projects template: {projects_prompt_template}")

        prompt = ChatPromptTemplate.from_template(projects_prompt_template)
        logger.debug(f"Prompt: {prompt}")
        
        chain = prompt | self.llm_cheap | ContentBlockParser()
        logger.debug(f"Chain created: {chain}")
        
        input_data = {
            "projects": self.resume.projects
        } if data is None else data
        output = chain.invoke(input_data)
        logger.debug(f"Chain invocation result: {output}")

        logger.debug("Side projects section generation completed")
        return output

    def generate_achievements_section(self, data = None) -> str:
        """
        Generate the achievements section of the resume.
        Args:
            data (dict): The achievements to use for generating the achievements section.
        Returns:
            str: The generated achievements section.
        """
        logger.debug("Starting achievements section generation")

        achievements_prompt_template = self._preprocess_template_string(self.strings.prompt_achievements)
        logger.debug(f"Achievements template: {achievements_prompt_template}")

        prompt = ChatPromptTemplate.from_template(achievements_prompt_template)
        logger.debug(f"Prompt: {prompt}")

        chain = prompt | self.llm_cheap | ContentBlockParser()
        logger.debug(f"Chain created: {chain}")

        input_data = {
            "achievements": self.resume.achievements,
            "certifications": self.resume.certifications,
        } if data is None else data
        logger.debug(f"Input data for the chain: {input_data}")

        output = chain.invoke(input_data)
        logger.debug(f"Chain invocation result: {output}")

        logger.debug("Achievements section generation completed")
        return output

    def generate_certifications_section(self, data = None) -> str:
        """
        Generate the certifications section of the resume.
        Returns:
            str: The generated certifications section.
        """
        logger.debug("Starting Certifications section generation")

        certifications_prompt_template = self._preprocess_template_string(self.strings.prompt_certifications)
        logger.debug(f"Certifications template: {certifications_prompt_template}")

        prompt = ChatPromptTemplate.from_template(certifications_prompt_template)
        logger.debug(f"Prompt: {prompt}")

        chain = prompt | self.llm_cheap | ContentBlockParser()
        logger.debug(f"Chain created: {chain}")

        input_data = {
            "certifications": self.resume.certifications
        } if data is None else data
        logger.debug(f"Input data for the chain: {input_data}")

        output = chain.invoke(input_data)
        logger.debug(f"Chain invocation result: {output}")

        logger.debug("Certifications section generation completed")
        return output
    
    def generate_additional_skills_section(self, data = None) -> str:
        """
        Generate the additional skills section of the resume.
        Returns:
            str: The generated additional skills section.
        """
        additional_skills_prompt_template = self._preprocess_template_string(self.strings.prompt_additional_skills)
        
        skills = set()
        if self.resume.experience_details:
            for exp in self.resume.experience_details:
                if exp.skills_acquired:
                    skills.update(exp.skills_acquired)

        if self.resume.education_details:
            for edu in self.resume.education_details:
                if edu.exam:
                    for exam in edu.exam:
                        skills.update(exam.keys())
        prompt = ChatPromptTemplate.from_template(additional_skills_prompt_template)
        chain = prompt | self.llm_cheap | ContentBlockParser()
        input_data = {
            "languages": self.resume.languages,
            "interests": self.resume.interests,
            "skills": skills,
        } if data is None else data
        output = chain.invoke(input_data)
        
        return output

    def generate_html_resume(self) -> str:
        """
        Generate the full HTML resume based on the resume object.
        Returns:
            str: The generated HTML resume.
        """
        def header_fn():
            if self.resume.personal_information:
                return self.generate_header()
            return ""

        def education_fn():
            if self.resume.education_details:
                return self.generate_education_section()
            return ""

        def work_experience_fn():
            if self.resume.experience_details:
                return self.generate_work_experience_section()
            return ""

        def projects_fn():
            if self.resume.projects:
                return self.generate_projects_section()
            return ""

        def achievements_fn():
            if self.resume.achievements:
                return self.generate_achievements_section()
            return ""
        
        def certifications_fn():
            if self.resume.certifications:
                return self.generate_certifications_section()
            return ""

        def additional_skills_fn():
            if (self.resume.experience_details or self.resume.education_details or
                self.resume.languages or self.resume.interests):
                return self.generate_additional_skills_section()
            return ""

        # Create a dictionary to map the function names to their respective callables
        functions = {
            "header": header_fn,
            "education": education_fn,
            "work_experience": work_experience_fn,
            "projects": projects_fn,
            "achievements": achievements_fn,
            "certifications": certifications_fn,
            "additional_skills": additional_skills_fn,
        }

        # Use ThreadPoolExecutor to run the functions in parallel
        with ThreadPoolExecutor() as executor:
            future_to_section = {executor.submit(fn): section for section, fn in functions.items()}
            results = {}
            for future in as_completed(future_to_section):
                section = future_to_section[future]
                try:
                    result = future.result()
                    if result:
                        results[section] = result
                except Exception as exc:
                    logger.error(f'{section} raised an exception: {exc}')
        full_resume = "<body>\n"
        full_resume += f"  {results.get('header', '')}\n"
        full_resume += "  <main>\n"
        full_resume += f"    {results.get('education', '')}\n"
        full_resume += f"    {results.get('work_experience', '')}\n"
        full_resume += f"    {results.get('projects', '')}\n"
        full_resume += f"    {results.get('achievements', '')}\n"
        full_resume += f"    {results.get('certifications', '')}\n"
        full_resume += f"    {results.get('additional_skills', '')}\n"
        full_resume += "  </main>\n"
        full_resume += "</body>"
        return full_resume
