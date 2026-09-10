from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DomainPack:
    """Lightweight taxonomy used to normalize a domain without creating a new Skill."""

    name: str
    taxonomy: dict[str, tuple[str, ...]] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    default_competency: str = "role_fundamentals"

    def enrich(self, title: str, content: str, metadata: dict[str, Any]) -> dict[str, Any]:
        result = dict(metadata)
        text = f"{title}\n{content}".casefold()
        matches = [
            topic for topic, terms in self.taxonomy.items()
            if any(term.casefold() in text for term in terms)
        ]
        if matches and not result.get("topic"):
            result["topic"] = matches[0]
        existing = result.get("competencies") or []
        if isinstance(existing, str):
            existing = [existing]
        result["competencies"] = list(dict.fromkeys([
            *existing, self.default_competency, *matches,
        ]))
        if not result.get("difficulty"):
            if any(term in text for term in ("生产级", "源码", "底层", "故障", "权衡", "高级")):
                result["difficulty"] = "advanced"
            elif any(term in text for term in ("原理", "设计", "实现", "优化")):
                result["difficulty"] = "intermediate"
        return result


class DomainPackRegistry:
    def __init__(self) -> None:
        common = {
            "RAG": ("rag", "检索增强", "rerank", "召回"),
            "Agent Runtime": ("agent runtime", "agent loop", "react", "执行循环"),
            "上下文工程": ("context engineering", "上下文工程", "token 预算"),
            "MCP/工具调用": ("mcp", "function calling", "工具调用"),
            "评测与可观测": ("评测", "evaluation", "可观测", "监控", "trace"),
            "安全": ("prompt 注入", "权限", "安全", "policy"),
            "记忆": ("长期记忆", "短期记忆", "memory"),
            "多 Agent": ("multi-agent", "multi agent", "多 agent", "多智能体"),
            "系统设计": ("系统设计", "架构", "高并发", "分布式"),
            "Python": ("python", "fastapi"),
            "Java": ("java", "jvm", "spring"),
            "前端": ("react", "typescript", "浏览器"),
            "算法": ("算法", "复杂度", "动态规划", "数据结构"),
        }
        self._packs = {
            "interview": DomainPack("interview", common),
            "ai_agent": DomainPack("ai_agent", common, default_competency="ai"),
            "backend": DomainPack("backend", common, default_competency="system_design"),
            "frontend": DomainPack("frontend", common, default_competency="language"),
            "algorithm": DomainPack("algorithm", common, default_competency="algorithm"),
        }

    def get(self, name: str | None) -> DomainPack:
        return self._packs.get(name or "interview", self._packs["interview"])

    def register(self, pack: DomainPack) -> None:
        if not pack.name.strip():
            raise ValueError("domain pack name cannot be empty")
        self._packs[pack.name] = pack
