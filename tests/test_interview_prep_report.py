from pathlib import Path

from backend.services import interview_service
from src.libs.interview_prep.interview_generator import InterviewPrepGenerator


def test_prompt_requires_role_analysis_and_quantified_fit():
    prompt = InterviewPrepGenerator._build_prompt("zh")

    assert "# 第一部分：岗位分析" in prompt
    assert "# 第二部分：面试准备报告" in prompt
    assert "0-100" in prompt
    assert "权重合计必须为 100%" in prompt
    assert "针对性提升计划" in prompt
    assert "所有章节合计必须严格生成 {question_count} 道问题" in prompt


def test_truncation_detection_supports_common_provider_reasons():
    class Result:
        structured_output = {"finish_reason": "max_tokens"}

    assert InterviewPrepGenerator._is_truncated(Result()) is True
    Result.structured_output = {"finish_reason": "length"}
    assert InterviewPrepGenerator._is_truncated(Result()) is True
    Result.structured_output = {"finish_reason": "end_turn"}
    assert InterviewPrepGenerator._is_truncated(Result()) is False


def test_markdown_pdf_writer_creates_pdf(tmp_path: Path):
    output = tmp_path / "report.pdf"

    interview_service._write_markdown_pdf(
        "# 第一部分：岗位分析\n\n## 匹配度\n\n- 总体匹配度：80/100",
        output,
        title="面试准备报告",
    )

    assert output.read_bytes().startswith(b"%PDF")
