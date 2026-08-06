from src.libs.ai_engine.harness import protect_education_section
from src.resume_schemas.resume import Resume


def test_missing_research_direction_cannot_be_invented_from_jd_output():
    generated = """
    <section id="education"><h2>教育背景</h2>
      <li>研究方向：AIGC 图像生成与计算摄影</li>
    </section>
    """
    result = protect_education_section(
        [{
            "education_level": "硕士",
            "institution": "中国科学院大学",
            "field_of_study": "人工智能",
            "start_date": "2024",
            "year_of_completion": "2027",
        }],
        generated,
    )

    assert "中国科学院大学" in result.html
    assert "人工智能" in result.html
    assert "研究方向" not in result.html
    assert "AIGC" not in result.html
    assert result.discarded_model_output is True


def test_declared_research_direction_is_preserved_verbatim():
    result = protect_education_section(
        [{
            "education_level": "硕士",
            "institution": "测试大学",
            "field_of_study": "计算机科学",
            "research_direction": "大语言模型智能体与工具调用",
            "research_topics": ["任务规划", "长期记忆"],
        }],
        "<section>研究方向：计算机视觉</section>",
    )

    assert "研究方向：</strong>大语言模型智能体与工具调用" in result.html
    assert "任务规划、长期记忆" in result.html
    assert "计算机视觉" not in result.html


def test_resume_schema_keeps_structured_education_facts():
    resume = Resume("""
personal_information: null
education_details:
  - education_level: Master's Degree
    institution: Test University
    field_of_study: Artificial Intelligence
    final_evaluation_grade: null
    start_date: '2024'
    year_of_completion: 2027
    research_direction: Agentic AI
    additional_info:
      relevant_courses: Machine Learning, NLP
      honors: Outstanding Student
experience_details: []
projects: []
achievements: []
certifications: []
languages: []
interests: []
""")

    education = resume.education_details[0]
    assert education.research_direction == "Agentic AI"
    assert education.additional_info.relevant_courses == "Machine Learning, NLP"
