import yaml

from backend.services.resume_selection import carry_experience_library, select_visible_experiences
from src.libs.ai_engine.harness.resume_quality import _patch_header


SOURCE = """\
personal_information:
  full_name: 测试用户
  email: user@example.com
education_details:
  - institution: 学校甲
    field_of_study: 计算机
  - institution: 学校乙
    field_of_study: 数学
experience_details:
  - company: 公司甲
    position: 工程师
  - company: 公司乙
    position: 研究员
projects:
  - name: 项目甲
    description: 甲项目事实
  - name: 项目乙
    description: 乙项目事实
"""


def test_quality_header_prefers_confirmed_full_name():
    result = _patch_header(
        "<header><h1>模型生成姓名</h1></header>",
        {"full_name": "测试用户", "name": "错误", "surname": "姓名"},
        "zh",
    )
    assert "<h1>测试用户</h1>" in result
    assert "错误姓名" not in result


def test_new_generation_uses_only_visible_experiences_in_dom_order():
    html = """<html><body><header><h1>测试用户</h1></header>
      <section id="education"><div class="entry" data-source-id="education-1">
        <span class="entry-name">学校乙</span></div></section>
      <section id="work-experience"><div class="entry" data-source-id="experience-1">
        <span class="entry-name">公司乙</span></div>
        <div class="entry" data-source-id="experience-0"><span class="entry-name">公司甲</span></div>
      </section>
      <section id="side-projects"><div class="entry" data-source-id="project-1">
        <span class="entry-name">项目乙</span></div></section>
      <div id="buping-experience-library-store" hidden>
        <div class="entry" data-source-id="project-0"><span class="entry-name">项目甲</span></div>
      </div>
    </body></html>"""
    selected = yaml.safe_load(select_visible_experiences(SOURCE, html))

    assert [item["institution"] for item in selected["education_details"]] == ["学校乙"]
    assert [item["company"] for item in selected["experience_details"]] == ["公司乙", "公司甲"]
    assert [item["name"] for item in selected["projects"]] == ["项目乙"]
    assert selected["projects"][0]["description"] == "乙项目事实"


def test_manually_added_experience_becomes_generation_source():
    html = """<html><body><header><h1>测试用户</h1></header>
      <section id="education"><div class="entry" data-source-id="education-0">
        <span class="entry-name">学校甲</span></div></section>
      <section id="work-experience"><div class="entry" data-buping-manual-experience="work">
        <span class="entry-name">新公司</span><span class="entry-location">上海</span>
        <span class="entry-title">后端工程师</span><span class="entry-year">2025-2026</span>
        <ul><li>完成接口开发与测试</li></ul></div></section>
      <section id="side-projects"><div class="entry" data-buping-manual-experience="project">
        <span class="entry-name">新项目</span><span class="entry-year">2026</span>
        <ul><li>实现任务调度</li></ul></div></section>
    </body></html>"""
    selected = yaml.safe_load(select_visible_experiences(SOURCE, html))

    assert selected["experience_details"] == [{
        "company": "新公司", "position": "后端工程师", "location": "上海",
        "employment_period": "2025-2026",
        "key_responsibilities": [{"responsibility": "完成接口开发与测试"}],
    }]
    assert selected["projects"] == [{
        "name": "新项目", "project_level": "", "project_role": "",
        "time_period": "2026", "description": "实现任务调度",
    }]


def test_no_current_version_keeps_original_source():
    assert select_visible_experiences(SOURCE, "") == SOURCE


def test_lightweight_yaml_preview_does_not_clear_source_experiences():
    preview = """<html><body><header><h1>测试用户</h1></header>
      <section><h2>Education</h2><div class="preview-item">学校甲</div></section>
      <section><h2>Experience</h2><div class="preview-item">公司甲</div></section>
    </body></html>"""
    assert select_visible_experiences(SOURCE, preview) == SOURCE


def test_reindexed_source_id_cannot_swap_experiences():
    html = """<html><body><header><h1>测试用户</h1></header>
      <section id="work-experience"><div class="entry" data-source-id="experience-0">
        <span class="entry-name">公司乙</span><span class="entry-title">研究员</span>
      </div></section></body></html>"""
    selected = yaml.safe_load(select_visible_experiences(SOURCE, html))
    assert selected["experience_details"] == [{"company": "公司乙", "position": "研究员"}]


def test_withdrawn_library_survives_new_generation_without_becoming_visible():
    current = """<html><body><header><h1>测试用户</h1></header>
      <div id="buping-experience-library-store" hidden>
        <div class="entry" data-buping-library-item="saved-1"
             data-buping-library-section-id="side-projects">
          <span class="entry-name">已撤下项目</span>
        </div>
      </div></body></html>"""
    generated = "<html><body><header><h1>测试用户</h1></header></body></html>"
    carried = carry_experience_library(current, generated)
    assert carried.count('id="buping-experience-library-store"') == 1
    assert 'data-buping-library-item="saved-1"' in carried
    selected = yaml.safe_load(select_visible_experiences(SOURCE, carried))
    assert selected["projects"] == []
