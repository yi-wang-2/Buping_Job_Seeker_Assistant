"""Mock interview module - simulate real interview conversations with an AI interviewer."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import BaseOutputParser


class _PlainTextParser(BaseOutputParser):
    """Simple parser that extracts text from LLM response."""

    def parse(self, result: Any) -> str:
        if hasattr(result, "content"):
            content = result.content
        else:
            content = result

        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                else:
                    parts.append(str(block))
            return "".join(parts).strip()
        return str(content).strip() if content else ""

    @property
    def _type(self) -> str:
        return "plain_text_parser"


class InterviewRound(Enum):
    """面试轮次类型"""
    OPENING = "开场白"            # 自我介绍 / 寒暄
    TECHNICAL = "技术问题"         # 技术深度
    BEHAVIORAL = "行为面试"       # 行为/STAR
    PROJECT = "项目深挖"          # 简历项目
    CASE_STUDY = "案例分析"        # 系统设计 / 案例
    REVERSE = "反问环节"          # 候选人提问
    CLOSING = "结束语"            # 礼貌结束


class InterviewStyle(Enum):
    """面试官风格"""
    FRIENDLY = "友善型"           # 氛围轻松，鼓励式
    PROFESSIONAL = "专业型"       # 严肃专业，直接
    PRESSURE = "压力型"           # 追问逼问，挑战
    ACADEMIC = "学术型"           # 深挖原理，理论
    CASUAL = "闲聊型"             # 随机应变


@dataclass
class CandidateProfile:
    """候选人画像"""
    name: str = "候选人"
    resume_text: str = ""
    years_experience: int = 0
    target_position: str = ""


@dataclass
class CompanyProfile:
    """公司画像"""
    name: str = "某公司"
    industry: str = ""
    culture: str = ""


@dataclass
class JobProfile:
    """岗位画像"""
    title: str = "某岗位"
    description: str = ""
    requirements: List[str] = field(default_factory=list)


@dataclass
class InterviewMessage:
    """单条消息"""
    role: str  # "interviewer" or "candidate"
    content: str
    timestamp: float
    round: InterviewRound
    feedback: Optional[str] = None


@dataclass
class MockInterviewSession:
    """模拟面试会话"""
    session_id: str
    candidate: CandidateProfile
    company: CompanyProfile
    job: JobProfile
    interview_type: str = "综合面试"
    style: InterviewStyle = InterviewStyle.PROFESSIONAL
    messages: List[InterviewMessage] = field(default_factory=list)
    started_at: float = 0.0
    ended_at: float = 0.0
    current_round: InterviewRound = InterviewRound.OPENING


def _create_chat_model(api_key: str, model_type: str, base_url: str, model_name: str = ""):
    """创建 LLM 模型（复用 interview_generator 的模式）"""
    if model_type == "anthropic":
        from langchain_anthropic import ChatAnthropic
        model = model_name or "MiniMax-M3"
        kwargs = {
            "model": model,
            "api_key": api_key,
            "temperature": 0.6,  # 稍高一些让对话更自然
            "max_tokens": 1024,  # 短回复不需要太长
        }
        if base_url:
            kwargs["base_url"] = base_url
        try:
            return ChatAnthropic(**kwargs)
        except TypeError:
            if "base_url" in kwargs:
                kwargs["anthropic_api_url"] = kwargs.pop("base_url")
            if "max_tokens" in kwargs:
                kwargs["max_tokens_to_sample"] = kwargs.pop("max_tokens")
            if "model" in kwargs:
                kwargs["model_name"] = kwargs.pop("model")
            return ChatAnthropic(**kwargs)

    from langchain_openai import ChatOpenAI
    model = model_name or "gpt-4o-mini"
    kwargs = {
        "model": model,
        "api_key": api_key,
        "temperature": 0.6,
        "max_tokens": 1024,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def _build_system_prompt(session: MockInterviewSession) -> str:
    """构建面试官系统提示词"""
    style_desc = {
        InterviewStyle.FRIENDLY: "友善亲切，营造轻松氛围，多用鼓励性语言",
        InterviewStyle.PROFESSIONAL: "专业严谨，问题直接，重点考察核心能力",
        InterviewStyle.PRESSURE: "高压追问，对回答中的疑点持续追问，考察抗压能力",
        InterviewStyle.ACADEMIC: "学术风格，深挖技术原理和底层实现",
        InterviewStyle.CASUAL: "轻松闲聊式，从日常对话中考察思维和表达",
    }

    return f"""你是一位资深的技术面试官，正在为 {session.company.name} 公司招聘 {session.job.title} 岗位。

【候选人简历】
{session.candidate.resume_text}

【岗位职责】
{session.job.description}

【公司信息】
- 公司：{session.company.name}
- 行业：{session.company.industry or "未知"}
- 文化：{session.company.culture or "未知"}

【面试信息】
- 面试类型：{session.interview_type}
- 面试官风格：{style_desc[session.style]}
- 当前轮次：{session.current_round.value}

【行为准则】
1. 像真实面试官一样提问，每次只问一个问题
2. 根据候选人简历设计有针对性的问题
3. 根据候选人回答决定是深入追问还是转向新话题
4. 保持对话自然流畅，不要像机器人
5. 单次回复控制在 100-200 字以内
6. 不要使用 Markdown 格式（不要用 * # - 等符号）
7. 用口语化的方式表达，像正常说话一样
8. 当前轮次决定问题类型：
   - 开场白：自我介绍、寒暄
   - 技术问题：考察专业技能
   - 行为面试：考察软技能和经历
   - 项目深挖：深挖简历中的项目
   - 案例分析：系统设计、方案设计
   - 反问环节：让候选人提问
   - 结束语：礼貌结束面试

请直接输出你要说的话，不要包含"面试官："等前缀。"""


def _next_round(session: MockInterviewSession) -> InterviewRound:
    """根据已进行的轮次决定下一轮"""
    interviewer_count = len([m for m in session.messages if m.role == "interviewer"])
    if interviewer_count < 2:
        return InterviewRound.OPENING
    elif interviewer_count < 5:
        return InterviewRound.PROJECT  # 先从项目开始，比较自然
    elif interviewer_count < 8:
        return InterviewRound.TECHNICAL
    elif interviewer_count < 10:
        return InterviewRound.BEHAVIORAL
    elif interviewer_count < 12:
        return InterviewRound.REVERSE
    else:
        return InterviewRound.CLOSING


def _build_dialogue_prompt(session: MockInterviewSession):
    """构造对话 Prompt（直接用 PromptValue 对象，不依赖模板变量）"""
    from langchain_core.prompt_values import StringPromptValue
    template = _build_system_prompt(session) + "\n\n"

    # 拼接对话历史
    for msg in session.messages[-12:]:
        if msg.role == "interviewer":
            template += f"面试官: {msg.content}\n"
        else:
            template += f"候选人: {msg.content}\n"

    template += "\n面试官:"
    # 用 StringPromptValue 包装，绕过模板变量检查
    return StringPromptValue(text=template)


def _generate_evaluation(session: MockInterviewSession, llm) -> str:
    """生成最终评估报告"""
    if not session.messages:
        return "## 评估\n\n对话为空，无法生成评估。"

    # 整理对话
    conversation = []
    for msg in session.messages:
        speaker = "面试官" if msg.role == "interviewer" else "候选人"
        conversation.append(f"{speaker}: {msg.content}")
    conversation_text = "\n".join(conversation)

    # 不用 f-string，避免 {} 被误识别
    # 改成手动拼接，确保模板里没有任何 {} 变量
    evaluation_template = """你是一位资深面试官，请根据以下模拟面试对话，对候选人进行全面评估。

【对话记录】
""" + conversation_text + """

【候选人简历】
""" + session.candidate.resume_text + """

【评估维度】
1. 总体评分（1-10分）
2. 核心优势（3点）
3. 需要改进（3点）
4. 技术能力评估
5. 沟通表达能力
6. 综合素质评价
7. 是否推荐进入下一轮（强烈推荐/推荐/待定/不推荐）
8. 准备建议（针对该岗位）

请用 Markdown 格式输出评估报告，使用清晰的标题和列表。"""

    # 直接用 StringPromptValue + llm.invoke
    from langchain_core.prompt_values import StringPromptValue
    prompt = StringPromptValue(text=evaluation_template)
    result = llm.invoke(prompt.to_messages() if hasattr(prompt, 'to_messages') else evaluation_template)
    return _PlainTextParser().parse(result)


class MockInterviewer:
    """模拟面试官"""

    def __init__(self, api_key: str, model_type: str = "anthropic",
                 base_url: str = "", model_name: str = ""):
        self.api_key = api_key
        self.model_type = model_type
        self.base_url = base_url
        self.model_name = model_name
        self.llm = None
        self.sessions: dict = {}
        # Fallback: 立即读取 config.py 中的默认值
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

    def _ensure_llm(self):
        """懒加载 LLM"""
        if self.llm is None:
            self.llm = _create_chat_model(
                self.api_key, self.model_type, self.base_url, self.model_name
            )

    def start_session(
        self,
        candidate: CandidateProfile,
        company: CompanyProfile,
        job: JobProfile,
        interview_type: str = "综合面试",
        style: InterviewStyle = InterviewStyle.PROFESSIONAL,
    ) -> MockInterviewSession:
        """开始一场模拟面试"""
        # Fallback api_key
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

        self._ensure_llm()

        session = MockInterviewSession(
            session_id=str(uuid.uuid4()),
            candidate=candidate,
            company=company,
            job=job,
            interview_type=interview_type,
            style=style,
            started_at=time.time(),
            current_round=InterviewRound.OPENING,
        )

        # 生成开场白（直接用 llm.invoke，避免 chain 的 dict 参数问题）
        prompt = _build_dialogue_prompt(session)
        result = self.llm.invoke(prompt.to_messages())
        opening = _PlainTextParser().parse(result)

        session.messages.append(InterviewMessage(
            role="interviewer",
            content=opening,
            timestamp=time.time(),
            round=InterviewRound.OPENING,
        ))

        self.sessions[session.session_id] = session
        return session

    def submit_answer(self, session_id: str, answer: str) -> InterviewMessage:
        """候选人提交回答"""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        # 确保 LLM 已初始化
        self._ensure_llm()
        if self.llm is None:
            raise RuntimeError("LLM not initialized. Please check API key and model configuration.")

        session = self.sessions[session_id]

        # 记录候选人回答
        session.messages.append(InterviewMessage(
            role="candidate",
            content=answer,
            timestamp=time.time(),
            round=session.current_round,
        ))

        # 推进到下一轮
        session.current_round = _next_round(session)

        # 生成下一个问题
        prompt = _build_dialogue_prompt(session)
        result = self.llm.invoke(prompt.to_messages())
        next_question = _PlainTextParser().parse(result)

        # 记录面试官问题
        question_msg = InterviewMessage(
            role="interviewer",
            content=next_question,
            timestamp=time.time(),
            round=session.current_round,
        )
        session.messages.append(question_msg)

        return question_msg

    def end_session(self, session_id: str) -> str:
        """结束会话，返回评估报告"""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        # 确保 LLM 已初始化
        self._ensure_llm()
        if self.llm is None:
            return "## 评估\n\nLLM 未初始化，请检查 API Key 和模型配置。"

        session = self.sessions[session_id]
        session.ended_at = time.time()

        return _generate_evaluation(session, self.llm)

    def get_history(self, session_id: str) -> List[InterviewMessage]:
        """获取会话历史"""
        if session_id not in self.sessions:
            return []
        return self.sessions[session_id].messages
