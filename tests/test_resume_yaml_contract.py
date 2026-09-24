from pathlib import Path

import yaml

from src.libs.resume_and_cover_builder import document_parser
from src.resume_schemas.resume import (
    EducationAdditionalInfo,
    EducationDetails,
    LegalAuthorization,
    PersonalInformation,
    Resume,
    WorkPreferences,
)


ROOT = Path(__file__).resolve().parents[1]


def _schema() -> dict:
    return yaml.safe_load((ROOT / "assets" / "resume_schema.yaml").read_text(encoding="utf-8"))


def test_empty_template_and_asset_schema_match_resume_model():
    expected_top_level = set(Resume.model_fields)

    assert set(document_parser._empty_resume()) == expected_top_level
    assert set(_schema()) - {"professional_summary"} == expected_top_level - {"professional_summary"}


def test_empty_v2_template_is_accepted_by_resume_model():
    content = yaml.safe_dump(document_parser._empty_resume(), allow_unicode=True)

    parsed = Resume(content)

    assert parsed.personal_information.email is None
    assert parsed.education_details == []


def test_nested_asset_schema_matches_pydantic_models():
    schema = _schema()

    assert set(schema["personal_information"]["properties"]) == set(PersonalInformation.model_fields)
    assert set(schema["education_details"]["items"]["properties"]) == set(EducationDetails.model_fields)
    assert set(
        schema["education_details"]["items"]["properties"]["additional_info"]["properties"]
    ) == set(EducationAdditionalInfo.model_fields)
    assert set(schema["legal_authorization"]["properties"]) == set(LegalAuthorization.model_fields)
    assert set(schema["work_preferences"]["properties"]) == set(WorkPreferences.model_fields)


def test_examples_round_trip_without_losing_supported_fields():
    for filename in ("plain_text_resume.yaml", "plain_text_resume_zh.yaml"):
        text = (ROOT / "data_folder_example" / filename).read_text(encoding="utf-8")
        normalized = document_parser.normalize_resume_data(yaml.safe_load(text))
        dumped = Resume(yaml.safe_dump(normalized, allow_unicode=True)).model_dump()

        assert set(dumped) == set(Resume.model_fields)
        assert "research_topics" in dumped["education_details"][0]
        assert "exam" in dumped["education_details"][0]


def test_legacy_yaml_upload_is_migrated_to_v2():
    legacy = b"""
personal_information:
  full_name: Test User
  email: test@example.com
education_details:
  - degree: Master
    university: Example University
    gpa: '4.0'
    graduation_year: '2027'
    additional_info:
      exam:
        Algorithms: A
certifications:
  - AWS
"""

    parsed = document_parser.parse_document("resume.yaml", legacy)
    education = parsed["education_details"][0]

    assert education["education_level"] == "Master"
    assert education["institution"] == "Example University"
    assert education["final_evaluation_grade"] == "4.0"
    assert education["year_of_completion"] == "2027"
    assert education["exam"] == {"Algorithms": "A"}
    assert "exam" not in education["additional_info"]
    assert parsed["certifications"] == [{"name": "AWS", "description": ""}]
    assert set(parsed) == set(Resume.model_fields)


def test_normalization_preserves_structured_technical_skills():
    parsed = document_parser.normalize_resume_data({
        "skills": [{
            "category": "AI/LLM 工程",
            "details": "熟悉 LangChain，具备 Agent Runtime 与上下文管理经验。",
        }],
    })

    assert parsed["skills"] == [{
        "category": "AI/LLM 工程",
        "details": "熟悉 LangChain，具备 Agent Runtime 与上下文管理经验。",
    }]


def test_pdf_visual_wraps_are_joined_inside_labeled_details():
    cleaned = document_parser._clean_extracted_text(
        "项目成果：完成算法部署，打通 RTSP 视频采集、图像推理、\n"
        "面积计算及数据库回传链路。\n"
        "技术栈\n"
        "AI/LLM 工程：熟悉 LangChain 与上下文管理。"
    )

    assert "项目成果:完成算法部署,打通 RTSP 视频采集、图像推理、面积计算及数据库回传链路。" in cleaned
    assert "\n技术栈\n" in cleaned


def test_pdf_compatibility_glyphs_are_normalized_before_label_detection():
    cleaned = document_parser._clean_extracted_text(
        "项⽬成果：支持 Fixed Workﬂow 与⻓上下文并完成\n工程化部署。\n语⾔能⼒：英语（CET-6）"
    )

    assert cleaned == "项目成果:支持 Fixed Workflow 与长上下文并完成工程化部署。\n语言能力:英语(CET-6)"


def test_document_parser_prompts_cover_every_canonical_field():
    field_names = set(Resume.model_fields)
    field_names.update(PersonalInformation.model_fields)
    field_names.update(EducationDetails.model_fields)
    field_names.update(EducationAdditionalInfo.model_fields)
    field_names.update(LegalAuthorization.model_fields)
    field_names.update(WorkPreferences.model_fields)

    for prompt in (document_parser._PROMPT_TEMPLATE_ZH, document_parser._PROMPT_TEMPLATE_EN):
        for field_name in field_names:
            assert f"{field_name}:" in prompt

    assert "无损信息抽取" in document_parser._PROMPT_TEMPLATE_ZH
    assert "不得压缩、概括" in document_parser._PROMPT_TEMPLATE_ZH
    assert "CET-6" in document_parser._PROMPT_TEMPLATE_ZH
    assert "lossless extraction" in document_parser._PROMPT_TEMPLATE_EN
