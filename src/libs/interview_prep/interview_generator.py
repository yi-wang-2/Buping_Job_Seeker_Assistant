"""Generate interview preparation materials from a resume and job description."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.output_parsers import BaseOutputParser
from langchain_core.prompts import ChatPromptTemplate


class ContentTextParser(BaseOutputParser):
    """Extract text content from plain strings, messages, or content block lists."""

    def parse(self, result: Any) -> str:
        if hasattr(result, "content"):
            result = result.content

        if isinstance(result, list):
            text_parts = []
            for block in result:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                else:
                    text_parts.append(str(block))
            return "".join(text_parts).strip()

        return str(result).strip() if result else ""

    @property
    def _type(self) -> str:
        return "content_text_parser"


@dataclass
class InterviewPrepGenerator:
    """LLM-backed interview prep generator."""

    api_key: str
    model_type: str = "anthropic"
    base_url: str = ""
    model_name: str = ""
    temperature: float = 0.4
    max_tokens: int = 4096

    def __post_init__(self):
        # Fallback: 如果没传 api_key / base_url / model_name，从 config.py 读取 (抄 llm_generate_resume.py 作业)
        try:
            import config as cfg
            if not self.api_key or self.api_key.startswith("sk-your-"):
                self.api_key = getattr(cfg, "ANTHROPIC_AUTH_TOKEN", "") or self.api_key
            if not self.base_url:
                self.base_url = getattr(cfg, "ANTHROPIC_BASE_URL", "")
            if not self.model_name:
                self.model_name = getattr(cfg, "ANTHROPIC_MODEL", "")
        except Exception:
            pass

    def generate(
        self,
        resume_text: str,
        job_description: str,
        interview_type: str,
        question_count: int,
        language: str = "zh",
    ) -> str:
        if not self.api_key:
            raise ValueError("API key is required.")
        if not resume_text.strip():
            raise ValueError("Resume content is empty.")
        if not job_description.strip():
            raise ValueError("Job description is required.")

        llm = self._create_chat_model()
        prompt = ChatPromptTemplate.from_template(self._build_prompt(language))
        chain = prompt | llm | ContentTextParser()

        return chain.invoke(
            {
                "resume_text": resume_text,
                "job_description": job_description,
                "interview_type": interview_type,
                "question_count": max(3, min(int(question_count), 20)),
            }
        )

    def _create_chat_model(self):
        if self.model_type == "anthropic":
            from langchain_anthropic import ChatAnthropic

            model = self.model_name or "MiniMax-M3"
            base_url = self.base_url or ""
            # 抄作业：和 llm_generate_resume.py 一样的调用方式
            try:
                if base_url:
                    return ChatAnthropic(model=model, api_key=self.api_key, base_url=base_url, temperature=self.temperature, max_tokens=self.max_tokens)
                return ChatAnthropic(model=model, api_key=self.api_key, temperature=self.temperature, max_tokens=self.max_tokens)
            except TypeError:
                try:
                    if base_url:
                        return ChatAnthropic(model=model, api_key=self.api_key, anthropic_api_url=base_url, temperature=self.temperature, max_tokens=self.max_tokens)
                    return ChatAnthropic(model=model, api_key=self.api_key, temperature=self.temperature, max_tokens=self.max_tokens)
                except TypeError:
                    return ChatAnthropic(model=model, api_key=self.api_key, temperature=self.temperature, max_tokens=self.max_tokens)

        from langchain_openai import ChatOpenAI

        model = self.model_name or "gpt-4o-mini"
        kwargs = {
            "model": model,
            "api_key": self.api_key,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return ChatOpenAI(**kwargs)

    @staticmethod
    def _build_prompt(language: str) -> str:
        if language == "en":
            return """
You are a senior technical interviewer and career coach. Generate a practical interview preparation report based only on the resume and job description below.

Resume:
{resume_text}

Job description:
{job_description}

Interview type: {interview_type}
Target number of questions: {question_count}

Return Markdown only. Use this structure:

# Interview Preparation

## 1. Role Focus
- Summarize the core expectations of the role.
- List the most important skills and signals to demonstrate.

## 2. Technical / Role Questions
For each question include:
- Question
- What it tests
- Answer strategy
- Resume evidence to use
- Risk to avoid

## 3. Resume Deep-Dive Questions
Focus on projects, work experience, metrics, tradeoffs, ownership, and failures.

## 4. Behavioral Questions Using STAR
For each question include a STAR answer outline.

## 5. Final Prep Checklist
Include company research, portfolio/resume talking points, questions to ask the interviewer, and last-minute practice items.

Rules:
- Do not invent companies, degrees, or experiences not supported by the resume.
- If evidence is missing, say what the candidate should prepare.
- Be concise but specific.
"""

        return """
你是一位资深技术面试官和求职教练。请只基于下面的简历内容和职位描述，生成一份可直接用于准备面试的 Markdown 报告。

简历内容：
{resume_text}

职位描述：
{job_description}

面试类型：{interview_type}
目标问题数量：{question_count}

请只返回 Markdown，并使用以下结构：

# 面试准备报告

## 1. 岗位画像
- 总结这个岗位最核心的能力要求。
- 列出候选人面试中最需要证明的技能、经验和信号。

## 2. 技术 / 岗位能力问题
每道题包含：
- 问题
- 考察点
- 回答思路
- 可引用的简历证据
- 需要避免的风险

## 3. 简历深挖问题
围绕项目经历、工作经历、技术取舍、量化结果、协作、失败复盘和个人贡献追问。

## 4. 行为面试问题（STAR）
每道题给出 STAR 回答框架：Situation、Task、Action、Result。

## 5. 面试前准备清单
包含公司调研、作品/简历讲解重点、可以反问面试官的问题、最后练习事项。

规则：
- 不要编造简历中不存在的公司、学历、经历或成果。
- 如果证据不足，请明确提示候选人需要提前补充准备。
- 内容要具体、可执行，避免空泛建议。
"""
