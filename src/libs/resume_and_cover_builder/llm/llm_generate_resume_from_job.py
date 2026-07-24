"""
Create a class that generates a job description based on a resume and a job description template.
"""
# app/libs/resume_and_cover_builder/llm_generate_resume_from_job.py
import os
from src.libs.resume_and_cover_builder.llm.llm_generate_resume import LLMResumer, ContentBlockParser
from src.libs.resume_and_cover_builder.utils import LoggerChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from loguru import logger
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

log_folder = 'log/resume/gpt_resum_job_descr'
if not os.path.exists(log_folder):
    os.makedirs(log_folder)
log_path = Path(log_folder).resolve()
logger.add(log_path / "gpt_resum_job_descr.log", rotation="1 day", compression="zip", retention="7 days", level="DEBUG")

class LLMResumeJobDescription(LLMResumer):
    def __init__(self, openai_api_key, strings):
        super().__init__(openai_api_key, strings)

    def set_job_description_from_text(self, job_description_text) -> None:
        """
        Set the job description text to be used for generating the resume.
        Args:
            job_description_text (str): The plain text job description to be used.
        """
        prompt = ChatPromptTemplate.from_template(self.strings.summarize_prompt_template)
        messages = prompt.format_messages(text=job_description_text)
        response = self.gateway_chat.invoke(
            messages,
            trace_metadata={"operation": "summarize_job_description"},
        )
        self.job_description = response.content.strip()
    
    def generate_all_sections(self) -> dict:
        """
        Generate all resume sections in a single LLM call with job description context.
        Returns:
            dict: A dictionary with section names as keys and generated HTML as values.
        """
        logger.debug("Starting unified resume generation with job description (single LLM call)")

        # Build a combined prompt that generates all sections at once, with job_description
        combined_prompt = """你是一位专业的HR专家和简历撰写顾问，专精于ATS友好型简历。
你的任务是在单次回复中生成一份完整、专业的简历，包含所有模块，并根据职位描述进行定制优化。

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
7. 根据【职位描述】调整内容：强调相关技能、经验和技术栈

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
<section id="technical-stack">
    <h2>技术栈</h2>
    <ul class="compact-list stack-list">
        <li><strong>编程语言：</strong>[具体掌握的语言及熟练程度]</li>
        <li><strong>图像处理/算法：</strong>[与职位描述最相关的算法、图像处理或ISP能力]</li>
        <li><strong>嵌入式/硬件：</strong>[与职位描述相关的嵌入式开发、传感器、硬件调试等能力]</li>
        <li><strong>平台与工具：</strong>[实际使用的平台、工具链和调试工具]</li>
    </ul>
</section>
<section id="languages-other">
    <h2>语言与其他</h2>
    <ul class="compact-list inline-list">
        <li><strong>语言能力：</strong>[中文、英文及证书/应用能力]</li>
        <li><strong>兴趣爱好：</strong>[简要列出兴趣爱好，可省略与岗位无关或过长内容]</li>
    </ul>
</section>
[/ADDITIONAL_SKILLS]

请基于以下数据和职位描述生成定制化简历：

【职位描述】（用于定制化）
{job_description}

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
1. 根据职位描述定制内容，强调最相关的技能和经验
2. 每个模块内容详实、专业，避免简单罗列
3. 善用量化和具体数据支撑描述
4. 突出与目标岗位最相关的经验和技能
5. 使用专业HR认可的语言和表达方式

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
            "job_description": self.job_description or "",
        }

        prompt = ChatPromptTemplate.from_template(combined_prompt)
        chain = prompt | self.llm_cheap | ContentBlockParser()
        
        logger.debug("Invoking unified LLM chain for all sections with job description")
        output = chain.invoke(input_data)
        logger.debug(f"Unified output length: {len(output)}")

        # Parse the output into individual sections
        sections = self._parse_unified_output(output)
        logger.debug(f"Parsed sections: {list(sections.keys())}")

        return sections

    def generate_header(self) -> str:
        """
        Generate the header section of the resume.
        Returns:
            str: The generated header section.
        """
        return super().generate_header(data={
            "personal_information": self.resume.personal_information,
            "job_description": self.job_description
        })

    def generate_education_section(self) -> str:
        """
        Generate the education section of the resume.
        Returns:
            str: The generated education section.
        """
        return super().generate_education_section(data={
            "education_details": self.resume.education_details,
            "job_description": self.job_description
        })

    def generate_work_experience_section(self) -> str:
        """
        Generate the work experience section of the resume.
        Returns:
            str: The generated work experience section.
        """
        return super().generate_work_experience_section(data={
            "experience_details": self.resume.experience_details,
            "job_description": self.job_description
        })

    def generate_projects_section(self) -> str:
        """
        Generate the side projects section of the resume.
        Returns:
            str: The generated side projects section.
        """
        return super().generate_projects_section(data={
            "projects": self.resume.projects,
            "job_description": self.job_description
        })

    def generate_achievements_section(self) -> str:
        """
        Generate the achievements section of the resume.
        Returns:
            str: The generated achievements section.
        """
        return super().generate_achievements_section(data={
            "achievements": self.resume.achievements,
            "job_description": self.job_description
        })


    def generate_certifications_section(self) -> str:
        """
        Generate the certifications section of the resume.
        Returns:
            str: The generated certifications section.
        """
        return super().generate_certifications_section(data={
            "certifications": self.resume.certifications,
            "job_description": self.job_description
        })

    def generate_additional_skills_section(self) -> str:
        """
        Generate the additional skills section of the resume.
        Returns:
            str: The generated additional skills section.
        """
        additional_skills_prompt_template = self._preprocess_template_string(
            self.strings.prompt_additional_skills
        )
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
        chain = prompt | self.llm_cheap | StrOutputParser()
        output = chain.invoke({
            "languages": self.resume.languages,
            "interests": self.resume.interests,
            "skills": skills,
            "job_description": self.job_description
        })
        return output
