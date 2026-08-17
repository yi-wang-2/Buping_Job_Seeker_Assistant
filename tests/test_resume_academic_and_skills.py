from src.libs.ai_engine.skills.builtin.resume_writer.prompts import build_resume_generation_prompt
from src.libs.ai_engine.harness.resume_facts import protect_resume_sections
from src.libs.resume_and_cover_builder.document_parser import normalize_resume_data
from src.libs.resume_and_cover_builder.llm.llm_generate_resume import LLMResumer


def test_resume_prompt_requires_contextual_skill_descriptions():
    prompt = build_resume_generation_prompt({"resume": {}, "target_pages": 1})

    assert "技能描述禁止写成" in prompt
    assert "能力层级、应用过程/场景和实践证据" in prompt
    assert "“精通”仅可在原始简历存在长期、深入且可核验的事实证据时使用" in prompt


def test_academic_achievements_are_normalized_and_passed_to_prompt():
    resume = normalize_resume_data({
        "academic_achievements": [{
            "type": "专利",
            "title": "一种时序预测方法",
            "status": "已授权",
            "link": "CN123456",
        }],
    })
    prompt = build_resume_generation_prompt({"resume": resume, "target_pages": 1})

    assert resume["academic_achievements"][0]["title"] == "一种时序预测方法"
    assert "一种时序预测方法" in prompt
    assert "仅当【学术成果】存在非空数据时生成" in prompt


def test_legacy_publication_patent_and_software_copyright_fields_are_migrated():
    resume = normalize_resume_data({
        "publications": [{"name": "多模态预测论文", "status": "已录用"}],
        "patents": ["一种图像处理方法"],
        "software_copyrights": [{"title": "求职助手软件", "link": "2026SR001"}],
    })

    assert [item["type"] for item in resume["academic_achievements"]] == ["论文", "专利", "软件著作权"]
    assert resume["academic_achievements"][0]["title"] == "多模态预测论文"


def test_unified_output_parser_supports_academic_section():
    generator = object.__new__(LLMResumer)
    sections = generator._parse_unified_output(
        "[ACADEMIC_ACHIEVEMENTS]<section id=\"academic-achievements\"><h2>学术成果</h2></section>[/ACADEMIC_ACHIEVEMENTS]"
    )

    assert "academic_achievements" in sections
    assert 'id="academic-achievements"' in sections["academic_achievements"]


def test_academic_section_is_grounded_and_omitted_without_source_data():
    source = {
        "academic_achievements": [{
            "type": "论文", "title": "多模态预测研究", "status": "已录用",
        }],
    }
    generated = {
        "academic_achievements": (
            '<section id="academic-achievements"><h2>学术成果</h2><ul>'
            '<li><strong>论文 · 多模态预测研究：</strong>已录用</li></ul></section>'
        ),
    }

    protected = protect_resume_sections(source, generated).sections["academic_achievements"]
    omitted = protect_resume_sections({}, generated).sections["academic_achievements"]

    assert "多模态预测研究" in protected
    assert omitted == ""
