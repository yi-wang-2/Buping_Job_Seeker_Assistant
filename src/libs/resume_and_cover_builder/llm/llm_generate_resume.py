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


try:
    proto = _resolve_protocol()
    if proto == "anthropic":
        from langchain_anthropic import ChatAnthropic as ChatModel
    else:
        from langchain_openai import ChatOpenAI as ChatModel
except Exception:
    # fallback to OpenAI Chat if imports fail
    from langchain_openai import ChatOpenAI as ChatModel


def _create_chat_model(api_key: str):
    proto = _resolve_protocol()

    if proto == "anthropic":
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
    model_name = (
        cfg.OPENAI_MODEL
        if proto == "openai_response" and getattr(cfg, "OPENAI_MODEL", None)
        else (cfg.LLM_MODEL or "gpt-4o-mini")
    )
    base_url = getattr(cfg, "OPENAI_BASE_URL", None) or cfg.LLM_API_URL or ""
    if base_url:
        try:
            return ChatModel(
                model_name=model_name,
                openai_api_key=api_key,
                base_url=base_url,
                temperature=0.4,
                max_tokens=4096,
            )
        except TypeError:
            return ChatModel(model_name=model_name, openai_api_key=api_key, base_url=base_url, temperature=0.4)
    try:
        return ChatModel(model_name=model_name, openai_api_key=api_key, temperature=0.4, max_tokens=4096)
    except TypeError:
        return ChatModel(model_name=model_name, openai_api_key=api_key, temperature=0.4)
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

    def generate_all_sections(self) -> dict:
        """
        Generate all resume sections in a single LLM call for better coherence.
        Returns:
            dict: A dictionary with section names as keys and generated HTML as values.
        """
        logger.debug("Starting unified resume generation (single LLM call)")

        # Build a combined prompt that generates all sections at once
        combined_prompt = """你是一位专业的HR专家和简历撰写顾问，专精于ATS友好型简历。
你的任务是在单次回复中生成一份完整、专业的简历，包含所有模块。

请使用以下标记符返回各模块：
[HEADER]...[/HEADER]
[EDUCATION]...[/EDUCATION]
[WORK_EXPERIENCE]...[/WORK_EXPERIENCE]
[PROJECTS]...[/PROJECTS]
[ACHIEVEMENTS]...[/ACHIEVEMENTS]
[CERTIFICATIONS]...[/CERTIFICATIONS]
[ADDITIONAL_SKILLS]...[/ADDITIONAL_SKILLS]

重要规则：
1. 每个模块必须用对应的开始标记和结束标记包裹，如[HEADER]...[/HEADER]
2. 包含所有有数据的模块，无数据的模块省略
3. 内容要专业、详细、有吸引力，避免简单罗列
4. 善用量化和具体数据支撑描述（如：提升效率30%、管理团队20人）
5. 语言专业流畅，展现应聘者的核心价值
6. 所有模块标题使用中文

模块模板：

[HEADER]
<header>
  <h1>[姓名]</h1>
  <div class="contact-info"> 
    <p class="fas fa-map-marker-alt">
      <span>[城市, 国家]</span>
    </p> 
    <p class="fas fa-phone">
      <span>[电话]</span>
    </p> 
    <p class="fas fa-envelope">
      <span>[邮箱]</span>
    </p> 
    <p class="fab fa-linkedin">
      <a href="[LinkedIn链接]">LinkedIn</a>
    </p> 
    <p class="fab fa-github">
      <a href="[GitHub链接]">GitHub</a>
    </p> 
  </div>
</header>
[/HEADER]

[EDUCATION]
<section id="education">
    <h2>教育背景</h2>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name">[大学名称]</span>
          <span class="entry-location">[位置]</span>
      </div>
      <div class="entry-details">
          <span class="entry-title">[学位] · [专业]</span>
          <span class="entry-year">[入学年] – [毕业年]</span>
      </div>
      <div class="grade">GPA: [你的GPA] | [其他重要成绩]</div>
      <ul class="compact-list">
          <li>核心课程：[课程名称]（成绩：[成绩]）</li>
          <li>核心课程：[课程名称]（成绩：[成绩]）</li>
          <li>核心课程：[课程名称]（成绩：[成绩]）</li>
      </ul>
    </div>
</section>
[/EDUCATION]

[WORK_EXPERIENCE]
<section id="work-experience">
    <h2>工作经验</h2>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name">[公司名称]</span>
          <span class="entry-location">[城市]</span>
      </div>
      <div class="entry-details">
          <span class="entry-title">[职位名称]</span>
          <span class="entry-year">[开始日期] – [结束日期]</span>
      </div>
      <ul class="compact-list">
          <li>[详细描述职责1，突出量化成果：如"主导XX系统开发，日均处理请求XX次，提升响应速度40%"</li>
          <li>[详细描述职责2，强调技术深度和团队协作：如"优化数据库查询性能，将慢查询减少60%"</li>
          <li>[详细描述职责3，展示职业成长：如"指导3名 junior 工程师，推动团队效率提升25%"</li>
      </ul>
    </div>
</section>
[/WORK_EXPERIENCE]

[PROJECTS]
<section id="side-projects">
    <h2>项目经验</h2>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name"><i class="fab fa-github"></i> <a href="[项目链接]">[项目名称]</a></span>
          <span class="entry-tech">[技术栈1 / 技术栈2 / 技术栈3]</span>
      </div>
      <ul class="compact-list">
          <li>[项目描述：简述项目背景、目标和你解决的核心问题]</li>
          <li>[技术贡献：详细说明你使用的技术方案、遇到的挑战及解决方案]</li>
          <li>[项目成果：量化成果，如"GitHub 500+ stars"、"日活用户10万+"</li>
      </ul>
    </div>
</section>
[/PROJECTS]

[ACHIEVEMENTS]
<section id="achievements">
    <h2>成就荣誉</h2>
    <ul class="compact-list">
      <li><strong>[奖项/荣誉名称]：</strong>[详细描述获奖原因、评选标准及排名情况，突出竞争性和含金量]</li>
      <li><strong>[竞赛/ Hackathon 名称]：</strong>[描述参与经历、担任角色、最终成绩或创新点]</li>
    </ul>
</section>
[/ACHIEVEMENTS]

[CERTIFICATIONS]
<section id="certifications">
    <h2>证书资质</h2>
    <ul class="compact-list">
      <li><strong>[证书名称]：</strong>[颁发机构] | [获得日期] | [证书编号或验证方式]</li>
      <li><strong>[专业认证]：</strong>[颁发机构] | [获得日期] | [简述该认证的专业价值]</li>
    </ul>
</section>
[/CERTIFICATIONS]

[ADDITIONAL_SKILLS]
<section id="skills-languages">
    <h2>其他技能</h2>
    <div class="two-column">
      <div class="skills-column">
          <h3>技术技能</h3>
          <ul class="compact-list">
              <li><strong>编程语言：</strong>[具体掌握的语言及熟练程度]</li>
              <li><strong>框架/工具：</strong>[实际使用的框架和工具]</li>
              <li><strong>其他：</strong>[其他相关技能]</li>
          </ul>
      </div>
      <div class="languages-column">
          <h3>语言能力</h3>
          <ul class="compact-list">
              <li><strong>[语言名称]：</strong>[读写听说是哪一级，如"CET-6"或"流利"</li>
          </ul>
      </div>
    </div>
</section>
[/ADDITIONAL_SKILLS]

请基于以下数据生成简历：

【个人信息】
{personal_information}

【教育背景】
{education_details}

【工作经验】
{experience_details}

【项目经历】
{projects}

【成就荣誉】
{achievements}

【证书资质】
{certifications}

【其他信息】
语言能力: {languages}
兴趣爱好: {interests}
技能特长: {skills}

请确保：
1. 每个模块内容详实、专业，避免简单罗列
2. 善用量化和具体数据支撑描述
3. 突出与目标岗位最相关的经验和技能
4. 使用专业HR认可的语言和表达方式

仅返回标记的模块内容，每个模块都要正确闭合。"""

        # Prepare input data
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

        input_data = {
            "personal_information": self.resume.personal_information,
            "education_details": self.resume.education_details or "N/A",
            "experience_details": self.resume.experience_details or "N/A",
            "projects": self.resume.projects or "N/A",
            "achievements": self.resume.achievements or "N/A",
            "certifications": self.resume.certifications or "N/A",
            "languages": self.resume.languages or "N/A",
            "interests": self.resume.interests or "N/A",
            "skills": skills or "N/A",
        }

        prompt = ChatPromptTemplate.from_template(combined_prompt)
        chain = prompt | self.llm_cheap | ContentBlockParser()
        
        logger.debug("Invoking unified LLM chain for all sections")
        output = chain.invoke(input_data)
        logger.debug(f"Unified output length: {len(output)}")

        # Parse the output into individual sections
        sections = self._parse_unified_output(output)
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
            (r'\[EDUCATION\]', r'\[/EDUCATION\]', 'education'),
            (r'\[WORK_EXPERIENCE\]', r'\[/WORK_EXPERIENCE\]', 'work_experience'),
            (r'\[PROJECTS\]', r'\[/PROJECTS\]', 'projects'),
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
        
        # Assemble the HTML resume
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
        
        logger.debug("Unified resume generation completed")
        return full_resume
