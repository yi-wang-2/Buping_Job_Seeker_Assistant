from pathlib import Path

import pytest

from backend.services import resume_service
from backend.services.resume_service import switch_resume_template
from src.libs.resume_and_cover_builder import resume_html
from src.libs.resume_and_cover_builder.resume_html import apply_template_branding
from src.libs.ai_engine.harness.resume_facts import protect_education_section
from src.libs.resume_and_cover_builder.style_manager import StyleManager


STYLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src/libs/resume_and_cover_builder/resume_style/style_ucas_academic.css"
)


@pytest.fixture(autouse=True)
def isolate_uploaded_photo(monkeypatch, tmp_path):
    monkeypatch.setattr(resume_html, "DATA_FOLDER", tmp_path)


def test_ucas_academic_style_is_discoverable_and_uses_separate_institutional_logo():
    styles = StyleManager().get_styles()
    css = STYLE_PATH.read_text(encoding="utf-8")

    assert styles["国科大模板"][0] == STYLE_PATH.name
    assert "@page { size: A4" in css
    assert "border-bottom: 2px solid var(--ucas-blue)" in css
    assert "body:has(.ucas-template-logo) > *" in css
    assert "max-width: calc(100% - 24px) !important" in css
    assert ".resume-photo-frame" in css
    assert ".ucas-template-logo" in css
    assert "data:image" not in css  # Embedded at render time, not resolved relative to an output file.
    assert "base64" not in css
    assert 'font-family: "Microsoft YaHei"' in css
    assert "--ucas-muted: #303030" in css
    assert "#education .entry-header" in css
    assert "grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr) minmax(0, 1.25fr)" in css
    assert "#education .entry > ul" in css
    assert "#work-experience .entry-title" in css
    assert "#side-projects .entry-title" in css
    assert "data-project-level" in css


def test_ucas_academic_style_switch_preserves_existing_user_content():
    source = (
        "<html><head><style>body { color: red; }</style></head><body>"
        "<header><h1>示例姓名</h1></header>"
        "<section id='education'><h2>教育背景</h2><p>示例学校</p></section>"
        "</body></html>"
    )

    result = switch_resume_template(source, "国科大模板")

    assert result["style"] == "国科大模板"
    assert "示例姓名" in result["html"]
    assert "示例学校" in result["html"]
    assert 'data-resume-style="国科大模板"' in result["html"]
    assert 'id="ucas-template-logo"' in result["html"]
    assert 'alt="中国科学院大学校徽"' in result["html"]

    switched_back = switch_resume_template(result["html"], "静蓝 · Calm Blue")
    assert "ucas-template-logo" not in switched_back["html"]
    assert "示例姓名" in switched_back["html"]


def test_ucas_branding_is_idempotent_and_only_embeds_in_selected_style():
    source = "<html><body><header><h1>示例姓名</h1></header></body></html>"
    once = apply_template_branding(source, STYLE_PATH.name)
    twice = apply_template_branding(once, STYLE_PATH.name)

    assert twice.count('id="ucas-template-logo"') == 1
    assert "data:image/jpeg;base64," in twice
    assert "示例姓名" in twice
    assert "ucas-template-logo" not in apply_template_branding(twice, "style_calm_blue.css")


def test_ucas_preview_embeds_only_synthetic_resume_data(monkeypatch, tmp_path):
    monkeypatch.setattr(resume_service, "DATA_FOLDER", tmp_path)
    (tmp_path / "plain_text_resume_zh.yaml").write_text(
        "personal_information:\n  full_name: 示例姓名\n"
        "education_details:\n  - institution: 示例学校\n",
        encoding="utf-8",
    )

    result = resume_service.generate_preview_html("国科大模板")

    assert result["style"] == "国科大模板"
    assert "示例姓名" in result["html"]
    assert "示例学校" in result["html"]
    assert 'id="ucas-template-logo"' in result["html"]
    assert "data:image/jpeg;base64," in result["html"]


def test_ucas_education_is_single_row_and_keeps_extra_facts_for_other_styles(monkeypatch, tmp_path):
    monkeypatch.setattr(resume_service, "DATA_FOLDER", tmp_path)
    (tmp_path / "plain_text_resume_zh.yaml").write_text(
        "personal_information:\n  full_name: 示例姓名\n"
        "education_details:\n  - institution: 示例学校\n"
        "    education_level: 硕士\n    field_of_study: 人工智能\n"
        "    start_date: '2024'\n    year_of_completion: 2027\n"
        "    research_direction: 时序预测\n"
        "    additional_info:\n      is_211: true\n"
        "      is_double_first_class: true\n      honors: 示例荣誉\n",
        encoding="utf-8",
    )
    preview = resume_service.generate_preview_html("国科大模板")["html"]
    assert 'class="preview-education-section"' in preview
    assert 'data-school-tier="211 · 双一流"' in preview
    assert '<div class="education-highlight"><strong>研究方向：</strong>时序预测</div>' in preview
    assert "时序预测" in preview  # CSS hides details without deleting source facts.

    guarded = protect_education_section([{
        "institution": "示例学校", "education_level": "硕士", "field_of_study": "人工智能",
        "location": "北京",
        "additional_info": {"is_211": True, "honors": "示例荣誉"},
    }]).html
    assert 'data-school-tier="211"' in guarded
    assert '<span class="entry-location">北京</span>' in guarded
    assert "示例荣誉" in guarded
    switched = switch_resume_template(f"<html><body><header></header>{guarded}</body></html>", "国科大模板")["html"]
    switched_back = switch_resume_template(switched, "静蓝 · Calm Blue")["html"]
    assert "示例荣誉" in switched_back


def test_ucas_preview_and_switch_embed_only_uploaded_user_photo(monkeypatch, tmp_path):
    (tmp_path / "resume_photo.png").write_bytes(b"synthetic-photo")
    monkeypatch.setattr(resume_service, "DATA_FOLDER", tmp_path)
    (tmp_path / "plain_text_resume_zh.yaml").write_text(
        "personal_information:\n  full_name: 示例姓名\n", encoding="utf-8"
    )

    preview = resume_service.generate_preview_html("国科大模板")["html"]
    source = "<html><head></head><body><header><h1>示例姓名</h1></header></body></html>"
    switched = switch_resume_template(source, "国科大模板")["html"]

    for html in (preview, switched):
        assert html.count('class="resume-photo-frame"') == 1
        assert 'src="data:image/png;base64,c3ludGhldGljLXBob3Rv"' in html
        assert 'id="ucas-template-logo"' in html


def test_saved_ucas_preview_refreshes_embedded_style_without_changing_content():
    source = (
        "<html><head><style id='resume-template-style' data-resume-style='国科大模板'>"
        "/*国科大模板$local://resume-templates*/ body{color:red}"
        "</style></head><body><header><h1>示例姓名</h1></header>"
        "<section><h2>教育背景</h2><p>示例学校</p></section></body></html>"
    )

    refreshed, style_name, changed = resume_service.refresh_saved_resume_preview_html(source)

    assert style_name == "国科大模板"
    assert changed is True
    assert "示例姓名" in refreshed and "示例学校" in refreshed
    assert "body{color:red}" not in refreshed
    assert "max-width: calc(100% - 24px)" in refreshed
    assert 'id="ucas-template-logo"' in refreshed
    assert source != refreshed  # A caller must explicitly save to replace the historical file.


def test_saved_non_ucas_preview_is_not_rewritten():
    source = "<html><head><style>body{color:red}</style></head><body>示例</body></html>"

    assert resume_service.refresh_saved_resume_preview_html(source) == (source, "", False)


def test_current_ucas_history_html_is_returned_unchanged():
    source = "<html><head><style>body{color:red}</style></head><body><header><h1>示例姓名</h1></header></body></html>"
    current = switch_resume_template(source, "国科大模板")["html"]

    assert resume_service.refresh_saved_resume_preview_html(current) == (current, "国科大模板", False)


def test_current_ucas_history_adds_newly_uploaded_photo(tmp_path):
    source = "<html><head></head><body><header><h1>示例姓名</h1></header></body></html>"
    current = switch_resume_template(source, "国科大模板")["html"]
    (tmp_path / "resume_photo.png").write_bytes(b"synthetic-photo")

    refreshed, style_name, changed = resume_service.refresh_saved_resume_preview_html(current)

    assert style_name == "国科大模板"
    assert changed is True
    assert refreshed.count('class="resume-photo-frame"') == 1
    assert 'src="data:image/png;base64,c3ludGhldGljLXBob3Rv"' in refreshed
    assert "示例姓名" in refreshed


def test_current_ucas_history_replaces_changed_backend_photo(tmp_path):
    (tmp_path / "resume_photo.png").write_bytes(b"old-photo")
    source = "<html><head></head><body><header><h1>示例姓名</h1></header></body></html>"
    current = switch_resume_template(source, "国科大模板")["html"]
    (tmp_path / "resume_photo.png").write_bytes(b"new-photo")

    refreshed, style_name, changed = resume_service.refresh_saved_resume_preview_html(current)

    assert style_name == "国科大模板"
    assert changed is True
    assert "b2xkLXBob3Rv" not in refreshed
    assert "bmV3LXBob3Rv" in refreshed
    assert refreshed.count('class="resume-photo-frame"') == 1
