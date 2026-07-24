"""Generate interview preparation materials from a resume and job description."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.output_parsers import BaseOutputParser


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

        target_count = max(3, min(int(question_count), 20))
        prompt = self._build_prompt(language).format(
            resume_text=resume_text,
            job_description=job_description,
            interview_type=interview_type,
            question_count=target_count,
        )
        model = self.model_name or ("MiniMax-M3" if self.model_type == "anthropic" else "gpt-4o-mini")
        from src.libs.ai_engine.memory import SQLiteMemoryRepository
        from src.libs.ai_engine.observability import JsonlTraceSink
        from src.libs.ai_engine.optimization import PromptCache
        from src.libs.ai_engine.providers import GatewayConfig, LLMGateway
        from src.libs.ai_engine.runtime import AIRuntime
        from src.libs.ai_engine.skills import SkillRegistry
        from src.libs.ai_engine.skills.builtin import InterviewCoachSkill

        repository = SQLiteMemoryRepository()
        cache = PromptCache(repository.path) if repository.get_setting("cache_enabled", True) else None
        gateway = LLMGateway(
            GatewayConfig(api_key=self.api_key, base_url=self.base_url, max_retries=2),
            trace_sink=JsonlTraceSink(),
        )
        registry = SkillRegistry()
        registry.register(InterviewCoachSkill())
        runtime = AIRuntime(gateway, registry, cache=cache)

        def execute(prepared_prompt: str):
            return runtime.execute("interview_coach", {
                "resume": resume_text,
                "job_description": job_description,
                "interview_type": interview_type,
                "question_count": target_count,
                "language": language,
                "prepared_prompt": prepared_prompt,
            }, provider=self.model_type, model=model)

        result = execute(prompt)
        if self._is_truncated(result):
            compact_instruction = (
                "\n\nIMPORTANT: Regenerate the entire report from the beginning in a concise form. "
                "The previous attempt hit the output limit. Complete every required section and produce "
                f"exactly {target_count} interview questions in total."
                if language == "en" else
                "\n\n重要：请从头重新生成一份更精炼但完整的报告。上一次生成达到了输出长度上限。"
                f"必须完成所有规定章节，所有问题章节合计严格生成 {target_count} 道面试问题。"
            )
            result = execute(prompt + compact_instruction)
            if self._is_truncated(result):
                raise RuntimeError("模型连续两次达到输出长度上限，请减少问题数量后重试。")
        return result.content

    @staticmethod
    def _is_truncated(result: Any) -> bool:
        structured = result.structured_output if isinstance(result.structured_output, dict) else {}
        reason = str(structured.get("finish_reason") or "").lower()
        return reason in {"length", "max_tokens", "max_output_tokens"}

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

The target is the TOTAL number of questions across all question sections, not the number per section. Allocate approximately 50% to technical/role questions, 30% to resume deep-dives, and 20% to behavioral questions. Number them continuously and produce exactly {question_count} questions in total.

Return Markdown only. Use this structure:

# Part 1: Role Analysis

## 1. What This Role Does
Explain its purpose, typical responsibilities, deliverables, stakeholders, and likely challenges in plain language.

## 2. Core Competencies
Rank the required competencies, explain why each matters, and distinguish must-haves from nice-to-haves.

## 3. Candidate Fit Assessment
- Give an overall match score from 0 to 100.
- Show a weighted scoring table whose weights total 100%, with requirement, weight, candidate evidence, gap, and score.
- State whether applying is recommended and explain the conclusion.
- Identify the strongest matches and the 3-5 most important gaps. Missing resume evidence is not proof of experience.

# Part 2: Interview Preparation Report

## 1. Targeted Improvement Plan
For every important gap, give concrete actions, suggested evidence or portfolio work, priority, and a realistic preparation sequence.

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
- Base every fit judgment on explicit JD requirements and resume evidence. Explain the scoring basis.
- Keep the report complete and concise. Finish every required section within the output limit.
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

目标问题数量是所有问题章节合计的总数，不是每个章节的问题数。请按大约 50% 技术/岗位问题、30% 简历深挖问题、20% 行为问题分配，连续编号，所有章节合计必须严格生成 {question_count} 道问题。

请只返回 Markdown，并使用以下结构：

# 第一部分：岗位分析

## 1. 岗位是做什么的
用求职者容易理解的语言说明岗位目标、日常职责、关键产出、协作对象和主要挑战。

## 2. 核心能力要求
按重要性列出核心能力，解释每项能力为什么重要，并区分必须项与加分项。

## 3. 候选人匹配度分析
- 给出 0-100 的总体匹配度。
- 提供量化评分表，包含能力/要求、权重、简历证据、差距、得分；权重合计必须为 100%。
- 明确说明是否建议应聘及理由。
- 总结最强匹配点，并指出 3-5 个最核心差距。简历未体现的能力只能标记为“缺少证据”，不能推定候选人具备。

# 第二部分：面试准备报告

## 1. 针对性提升计划
针对每个核心差距，给出具体行动、可补充的案例或作品、优先级和建议准备顺序。

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
- 所有匹配判断必须同时引用 JD 要求和简历证据，并解释量化评分依据。
- 控制篇幅并保证报告完整，必须在输出限制内完成所有规定章节。
- 内容要具体、可执行，避免空泛建议。
"""
