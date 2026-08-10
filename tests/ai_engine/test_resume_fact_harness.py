from src.libs.ai_engine.harness import (
    FactPolicy,
    policy_for,
    protect_education_section,
    protect_resume_sections,
    validate_grounded_text,
)
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


def test_fact_policy_classifies_locked_soft_and_generative_fields():
    assert policy_for("personal_information.full_name") is FactPolicy.LOCKED
    assert policy_for("education_details.0.research_direction") is FactPolicy.LOCKED
    assert policy_for("experience_details.0.key_responsibilities") is FactPolicy.GROUNDED_REWRITE
    assert policy_for("experience_details.0.skills_acquired") is FactPolicy.GROUNDED_REWRITE
    assert policy_for("projects.0.description") is FactPolicy.GROUNDED_REWRITE
    assert policy_for("professional_summary") is FactPolicy.GENERATIVE


def test_full_resume_guard_blocks_identity_skills_numbers_and_missing_entries():
    source = {
        "personal_information": {
            "name": "旺",
            "surname": "易",
            "phone_prefix": "+86",
            "phone": "12345678",
            "email": "truth@example.com",
            "github": "",
        },
        "education_details": [],
        "experience_details": [{
            "position": "工程师",
            "company": "事实公司",
            "employment_period": "2021-2023",
            "location": "重庆",
            "key_responsibilities": [{"responsibility": "参与相机效果优化"}],
            "skills_acquired": ["图像处理"],
        }],
        "projects": [
            {"name": "项目甲", "description": "完成图像处理模块", "link": ""},
            {"name": "不能遗漏的项目乙", "description": "完成数据分析", "link": ""},
        ],
        "achievements": [{"name": "真实奖项", "description": "二等奖"}],
        "certifications": [{"name": "真实证书", "description": ""}],
        "languages": [{"language": "英语", "proficiency": "CET-6"}],
        "interests": ["阅读"],
    }
    generated = {
        "header": '<header><h1>错误姓名</h1><a href="https://github.com/fake">GitHub</a></header>',
        "work_experience": """
          <div class="entry"><span>事实公司</span><span>工程师</span><ul>
          <li>主导 PyTorch 系统建设，使效率提升 40%</li></ul></div>
        """,
        "projects": """
          <div class="entry"><span>项目甲</span><ul><li>精通 TensorFlow，服务 10 万用户</li></ul></div>
        """,
        "achievements": "<li>全国第一</li>",
        "certifications": "<li>CET-6 顶会论文无障碍阅读</li>",
        "additional_skills": "<li>PyTorch / TensorFlow / SQL</li>",
        "summary": "拥有 10 年经验，精通 PyTorch",
    }

    result = protect_resume_sections(source, generated, language="zh")
    html = "".join(result.sections.values())

    assert "<h1>旺易</h1>" in html
    assert "truth@example.com" in html
    assert "github.com/fake" not in html
    # Reasonable inferred skills remain allowed; only fabricated hard facts and
    # unverifiable numeric/contact claims are blocked.
    assert "PyTorch" in html
    assert "TensorFlow" in html
    assert "40%" not in html
    assert "10 年" not in html
    assert "参与相机效果优化" in html
    assert "不能遗漏的项目乙" in html
    assert "真实奖项" in html and "全国第一" in html
    assert "真实证书" in html and "顶会论文" not in html
    assert "图像处理" in html
    assert result.blocked_count >= 3


def test_confirmed_full_name_is_rendered_verbatim():
    result = protect_resume_sections({
        "personal_information": {"full_name": "用户确认姓名", "name": "错", "surname": "误"},
        "education_details": [], "experience_details": [], "projects": [],
        "achievements": [], "certifications": [], "languages": [], "interests": [],
    })
    assert "<h1>用户确认姓名</h1>" in result.sections["header"]
    assert "错误" not in result.sections["header"]


def test_generated_prose_rejects_new_numbers_but_allows_soft_reframing():
    source = "参与图像处理模块优化，准确率达到98.89%"
    assert validate_grounded_text(source, source) == []
    reasons = validate_grounded_text(source, "主导 PyTorch 模型优化，准确率达到99.9%")
    assert any("numeric" in reason for reason in reasons)


def test_grounded_rewrite_allows_polish_and_reasonable_inferred_skill():
    source = "完成图像处理模型训练与部署"

    assert validate_grounded_text(
        source,
        "基于 PyTorch 完成图像处理模型训练与部署，优化工程实现路径",
    ) == []
    assert validate_grounded_text(
        "负责用户需求分析与产品功能设计",
        "围绕用户需求开展系统分析，推动产品功能方案落地并持续优化使用体验",
    ) == []


def test_generated_prose_allows_unrelated_skill_claim_as_soft_content():
    assert validate_grounded_text(
        "完成图像处理模型训练与部署",
        "使用 Kubernetes 构建云原生集群",
    ) == []


def test_entry_guard_keeps_safe_bullet_when_sibling_claim_is_fabricated():
    source = {
        "personal_information": {"full_name": "测试用户"},
        "education_details": [],
        "experience_details": [{
            "company": "事实公司",
            "position": "算法工程师",
            "employment_period": "2023-2025",
            "location": "上海",
            "industry": "图像处理",
            "key_responsibilities": [{"responsibility": "完成图像处理模型训练与部署"}],
            "skills_acquired": ["深度学习"],
        }],
        "projects": [], "achievements": [], "certifications": [],
        "languages": [], "interests": [],
    }
    generated = {"work_experience": """
      <div class="entry"><span>事实公司</span><span>算法工程师</span><ul>
        <li>基于 PyTorch 完成图像处理模型训练与部署，优化工程实现路径</li>
        <li>服务 100 万用户并提升效率 90%</li>
      </ul></div>
    """}

    result = protect_resume_sections(source, generated, language="zh")

    assert "PyTorch" in result.sections["work_experience"]
    assert "100 万" not in result.sections["work_experience"]
    assert result.blocked_count == 1


def test_inferred_skill_and_proficiency_can_enter_soft_skill_section():
    source = {
        "personal_information": {"full_name": "测试用户"},
        "education_details": [],
        "experience_details": [{
            "company": "事实公司", "position": "算法工程师",
            "employment_period": "2023-2025", "location": "上海",
            "industry": "人工智能",
            "key_responsibilities": [{"responsibility": "完成深度学习模型训练与部署"}],
            "skills_acquired": [],
        }],
        "projects": [], "achievements": [], "certifications": [],
        "languages": [], "interests": [],
    }
    generated = {"additional_skills": """
      <section id="technical-stack"><ul>
        <li><strong>平台与工具：</strong>PyTorch</li>
        <li><strong>能力等级：</strong>精通 Kubernetes</li>
      </ul></section>
    """}

    result = protect_resume_sections(source, generated, language="zh")

    assert "PyTorch" in result.sections["additional_skills"]
    assert "Kubernetes" in result.sections["additional_skills"]
    assert result.blocked_count == 0


def test_award_name_stays_locked_while_generated_description_is_kept():
    source = {
        "personal_information": {"full_name": "测试用户"},
        "education_details": [], "experience_details": [], "projects": [],
        "achievements": [{"name": "真实奖项", "description": "创新项目获奖"}],
        "certifications": [], "languages": [], "interests": [],
    }
    generated = {
        "achievements": "<ul><li><strong>真实奖项：</strong>凭借创新方案与完整落地表现获得认可</li></ul>"
    }

    result = protect_resume_sections(source, generated, language="zh")

    assert "真实奖项" in result.sections["achievements"]
    assert "完整落地表现获得认可" in result.sections["achievements"]
    assert result.blocked_count == 0


def test_guard_patches_hard_facts_without_flattening_generated_html():
    source = {
        "personal_information": {"full_name": "真实姓名", "email": "truth@example.com"},
        "education_details": [],
        "experience_details": [{
            "company": "真实公司", "position": "高级工程师",
            "employment_period": "2023-2025", "location": "上海",
            "industry": "人工智能",
            "key_responsibilities": [{"responsibility": "负责模型训练与部署"}],
            "skills_acquired": ["Python"],
        }],
        "projects": [{"name": "真实项目", "link": "https://example.com/real", "description": "构建检索服务"}],
        "achievements": [], "certifications": [], "languages": [], "interests": [],
    }
    generated = {
        "header": '<header class="hero"><h1>错误姓名</h1><div class="contact-info"><p class="fas fa-envelope"><span>fake@example.com</span></p></div></header>',
        "work_experience": '''
          <section id="work-experience" class="polished"><h2><span>核心经历</span></h2>
            <div class="entry featured"><div class="entry-header">
              <span class="entry-name">错误公司</span><span class="entry-location">北京</span></div>
              <div class="entry-details"><span class="entry-title">错误职位</span><span class="entry-year">2099</span></div>
              <ul class="compact-list"><li><strong>模型工程：</strong>基于 <em>PyTorch</em> 完成训练与部署</li></ul>
            </div></section>
        ''',
        "projects": '''
          <section id="side-projects" data-layout="rich"><div class="entry card">
            <div class="entry-header"><span class="entry-name"><i class="fab fa-github"></i><a href="https://fake.example">错误项目</a></span>
            <span class="entry-tech"><b>RAG</b> / FastAPI</span></div>
            <ul><li><mark>检索增强：</mark>构建检索服务</li></ul></div></section>
        ''',
        "additional_skills": '<section id="technical-stack"><ul><li><strong>平台与工具：</strong><em>Docker</em> / Kubernetes</li></ul></section>',
    }

    result = protect_resume_sections(source, generated, language="zh")

    work = result.sections["work_experience"]
    assert 'class="polished"' in work and 'class="entry featured"' in work
    assert "<strong>模型工程：</strong>" in work and "<em>PyTorch</em>" in work
    assert "真实公司" in work and "高级工程师" in work and "2023-2025" in work
    assert "错误公司" not in work and "2099" not in work
    assert 'data-source-id="experience-0"' in work

    projects = result.sections["projects"]
    assert 'data-layout="rich"' in projects and 'class="entry card"' in projects
    assert '<span class="entry-tech"><b>RAG</b> / FastAPI</span>' in projects
    assert "<mark>检索增强：</mark>" in projects
    assert 'href="https://example.com/real"' in projects and "真实项目" in projects
    assert 'data-source-id="project-0"' in projects

    assert '<em>Docker</em>' in result.sections["additional_skills"]
    assert 'class="hero"' in result.sections["header"]
    assert "真实姓名" in result.sections["header"] and "truth@example.com" in result.sections["header"]


def test_guard_removes_only_the_invalid_claim_and_keeps_sibling_markup():
    source = {
        "personal_information": {"full_name": "测试用户"},
        "education_details": [],
        "experience_details": [{
            "company": "事实公司", "position": "工程师", "employment_period": "2024-2025",
            "location": "上海", "key_responsibilities": [{"responsibility": "完成服务重构"}],
            "skills_acquired": [],
        }],
        "projects": [], "achievements": [], "certifications": [], "languages": [], "interests": [],
    }
    generated = {"work_experience": '''
      <section id="work-experience"><div class="entry"><span class="entry-name">事实公司</span>
        <span class="entry-location">上海</span><span class="entry-title">工程师</span><span class="entry-year">2024-2025</span>
        <ul><li class="safe"><strong>架构：</strong>完成<em>服务重构</em></li>
        <li class="fake">性能提升 99%</li></ul></div></section>
    '''}

    result = protect_resume_sections(source, generated, language="zh")

    assert 'class="safe"' in result.sections["work_experience"]
    assert "<em>服务重构</em>" in result.sections["work_experience"]
    assert 'class="fake"' not in result.sections["work_experience"]
    assert result.blocked_count == 1
