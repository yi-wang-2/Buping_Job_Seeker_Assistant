from src.libs.ai_engine.harness import (
    GOLDEN_RESUME_WRITING_GUIDE,
    evaluate_resume_candidate,
    generate_candidates,
    protect_hard_facts_in_place,
    select_best_candidate,
)
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from src.libs.resume_and_cover_builder.llm.llm_generate_resume import LLMResumer


def _resume():
    return {
        "personal_information": {
            "name": "易", "surname": "旺", "country": "中国", "city": "",
            "phone_prefix": "+86", "phone": "13800000000", "email": "truth@example.com",
            "github": "https://github.com/real", "linkedin": "", "wechat": "",
        },
        "education_details": [{
            "education_level": "硕士", "institution": "中国科学院大学",
            "field_of_study": "人工智能", "start_date": "2024", "year_of_completion": "2027",
            "final_evaluation_grade": "", "exam": [],
        }],
        "experience_details": [{
            "company": "真实公司", "position": "影像效果工程师", "location": "重庆",
            "employment_period": "2021-2023", "industry": "图像处理",
            "key_responsibilities": [{"responsibility": "负责系统相机效果优化与交付"}],
            "skills_acquired": ["ISP Tuning"],
        }],
        "projects": [{
            "name": "真实项目", "description": "完成图像处理模块并通过验收",
            "link": "https://example.com/real",
        }],
        "achievements": [{"name": "真实奖项", "description": "省级二等奖"}],
        "certifications": [{"name": "计算机二级C", "description": ""}],
        "languages": [{"language": "英语", "proficiency": "CET-6"}],
        "interests": ["阅读"],
    }


def _candidate(work_item: str, project_item: str):
    return {
        "header": '<header><h1>易旺</h1></header>',
        "education": '<section id="education"><div class="entry"><span class="entry-name">中国科学院大学</span><span class="entry-title">硕士 · 人工智能</span><span class="entry-year">2024 – 2027</span></div></section>',
        "work_experience": f'<section id="work-experience"><div class="entry"><span class="entry-name">真实公司</span><span class="entry-title">影像效果工程师</span><span class="entry-year">2021-2023</span><ul>{work_item}</ul></div></section>',
        "projects": f'<section id="side-projects"><div class="entry"><span class="entry-name">真实项目</span><ul>{project_item}</ul></div></section>',
        "achievements": '<section id="achievements"><li><strong>真实奖项：</strong>省级二等奖</li></section>',
        "certifications": '<section id="certifications"><li><strong>计算机二级C：</strong>已获得</li></section>',
        "additional_skills": '<section id="technical-stack"><li><strong>平台与工具：</strong>ISP Tuning</li></section>',
    }


def test_golden_guide_contains_required_narrative_contract():
    assert "核心职责" in GOLDEN_RESUME_WRITING_GUIDE
    assert "项目管理" in GOLDEN_RESUME_WRITING_GUIDE
    assert "项目背景" in GOLDEN_RESUME_WRITING_GUIDE
    assert "严禁编造" in GOLDEN_RESUME_WRITING_GUIDE


def test_scorer_prefers_golden_structure_over_generic_hype():
    golden = _candidate(
        '<li><strong>核心职责：</strong>负责系统相机效果优化与交付</li>',
        '<li><strong>项目背景：</strong>面向图像处理交付场景建设核心模块</li>'
        '<li><strong>项目成果：</strong>完成图像处理模块并通过验收</li>',
    )
    generic = _candidate(
        '<li>深度赋能公司业务并打造现象级、行业领先的技术能力</li>',
        '<li>全方位赋能项目并获得市场高度认可</li>',
    )

    golden_score = evaluate_resume_candidate(golden, _resume()).score
    generic_score = evaluate_resume_candidate(generic, _resume()).score

    assert golden_score > generic_score
    assert select_best_candidate([generic, golden], _resume()).sections == golden


def test_candidate_generator_runs_three_independent_attempts():
    calls = []

    def invoke():
        calls.append(len(calls))
        return f"candidate-{len(calls)}"

    outputs = generate_candidates(invoke, count=3)

    assert len(calls) == 3
    assert len(outputs) == 3


def test_hard_fact_guard_patches_in_place_and_preserves_rich_html():
    candidate = _candidate(
        '<li class="kept"><strong>核心职责：</strong>使用 <em>ISP Tuning</em> 完成系统相机效果优化与交付</li>'
        '<li class="fake"><strong>项目成果：</strong>效率提升 99%</li>',
        '<li><strong>项目背景：</strong><mark>完成图像处理模块并通过验收</mark></li>',
    )
    candidate["header"] = '''<header class="hero"><h1>错误姓名</h1><div class="contact-info">
      <p class="fas fa-envelope"><span>fake@example.com</span></p>
      <p class="fab fa-github"><a href="https://fake.example">GitHub</a></p></div></header>'''
    candidate["work_experience"] = candidate["work_experience"].replace("真实公司", "错误公司")
    candidate["projects"] = candidate["projects"].replace(
        '<span class="entry-name">真实项目</span>',
        '<span class="entry-name"><i class="fab fa-github"></i><a href="https://fake.example">错误项目</a></span>',
    )

    result = protect_hard_facts_in_place(candidate, _resume())

    assert 'class="hero"' in result.sections["header"]
    assert "易旺" in result.sections["header"] and "truth@example.com" in result.sections["header"]
    assert "https://github.com/real" in result.sections["header"]
    assert "真实公司" in result.sections["work_experience"] and "错误公司" not in result.sections["work_experience"]
    assert '<li class="kept">' in result.sections["work_experience"]
    assert "<em>ISP Tuning</em>" in result.sections["work_experience"]
    assert 'class="fake"' not in result.sections["work_experience"]
    assert "真实项目" in result.sections["projects"] and "https://example.com/real" in result.sections["projects"]
    assert "<mark>完成图像处理模块并通过验收</mark>" in result.sections["projects"]
    assert result.violations


def test_hard_fact_guard_removes_invented_research_direction_only():
    candidate = _candidate(
        '<li><strong>核心职责：</strong>负责系统相机效果优化与交付</li>',
        '<li><strong>项目成果：</strong>完成图像处理模块并通过验收</li>',
    )
    candidate["education"] = '''<section id="education" class="golden"><div class="entry">
      <span class="entry-name">错误学校</span><span class="entry-title">错误专业</span>
      <span class="entry-year">2099</span><ul><li>研究方向：根据JD推断的大语言模型</li>
      <li class="style-kept">参与课程学习与工程实践</li></ul></div></section>'''

    result = protect_hard_facts_in_place(candidate, _resume())

    assert "中国科学院大学" in result.sections["education"]
    assert "硕士 · 人工智能" in result.sections["education"]
    assert "研究方向" not in result.sections["education"]
    assert 'class="style-kept"' in result.sections["education"]
    assert 'class="golden"' in result.sections["education"]


def test_llm_resumer_pipeline_selects_candidates_then_applies_guard():
    calls = []
    output = '''
    [HEADER]<header><h1>错误姓名</h1></header>[/HEADER]
    [EDUCATION]<section id="education"><div class="entry"><span class="entry-name">错误学校</span><span class="entry-title">硕士 · 错误专业</span><span class="entry-year">2099</span></div></section>[/EDUCATION]
    [WORK_EXPERIENCE]<section id="work-experience"><div class="entry"><span class="entry-name">错误公司</span><span class="entry-location">北京</span><span class="entry-title">错误职位</span><span class="entry-year">2099</span><ul><li><strong>核心职责：</strong>负责系统相机效果优化与交付</li></ul></div></section>[/WORK_EXPERIENCE]
    [PROJECTS]<section id="side-projects"><div class="entry"><span class="entry-name">错误项目</span><ul><li><strong>项目成果：</strong>完成图像处理模块并通过验收</li></ul></div></section>[/PROJECTS]
    [ACHIEVEMENTS]<section id="achievements"><li><strong>真实奖项：</strong>省级二等奖</li></section>[/ACHIEVEMENTS]
    [CERTIFICATIONS]<section id="certifications"><li><strong>计算机二级C：</strong>已获得</li></section>[/CERTIFICATIONS]
    [ADDITIONAL_SKILLS]<section id="technical-stack"><li><strong>平台与工具：</strong>ISP Tuning</li></section>[/ADDITIONAL_SKILLS]
    '''

    def fake_model(_messages):
        calls.append(1)
        return output

    resumer = LLMResumer.__new__(LLMResumer)
    resumer.resume = _resume()
    resumer.llm_cheap = RunnableLambda(fake_model)
    prompt = ChatPromptTemplate.from_template("generate {value}")

    sections = resumer._generate_best_sections(prompt, {"value": "resume"}, operation="test")

    assert len(calls) == 3
    assert "易旺" in sections["header"]
    assert "中国科学院大学" in sections["education"]
    assert "真实公司" in sections["work_experience"]
    assert "真实项目" in sections["projects"]
