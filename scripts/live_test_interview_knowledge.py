from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from backend.services.interview_service import _get_effective_config
from src.libs.interview_prep import InterviewPrepGenerator


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    config = _get_effective_config()
    generator = InterviewPrepGenerator(
        api_key=config["api_key"], model_type=config["model_type"],
        base_url=config["base_url"], model_name=config["model_name"], max_tokens=3000,
    )
    report = generator.generate(
        resume_text=(
            "目标岗位：AI Agent 开发工程师\n"
            "项目：设计 AI Runtime、Skill Runner、上下文 Token 预算、RAG 与事实校验 Harness。\n"
            "技术栈：Python、FastAPI、LangChain、SQLite、React。"
        ),
        job_description=(
            "AI Agent 开发工程师\n"
            "负责 Agent Runtime、RAG、上下文工程、工具调用、评测和生产可观测性。"
        ),
        interview_type="技术面试", question_count=3, language="zh",
        selected_knowledge_source_ids=["agent-interview-hub"],
    )
    citations = re.findall(r"\[K:([^\]]+)\]", report)
    output = ROOT / "artifacts" / "interview-knowledge-live-report.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    summary = {
        "report_characters": len(report), "citations": len(citations),
        "unique_citations": len(set(citations)), "output": str(output),
    }
    print(json.dumps(summary, ensure_ascii=False))
    if not citations:
        raise SystemExit("live report did not contain knowledge citations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
