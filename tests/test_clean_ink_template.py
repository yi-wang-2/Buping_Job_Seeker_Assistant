from pathlib import Path

from src.libs.resume_and_cover_builder.style_manager import StyleManager


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STYLE_PATH = (
    PROJECT_ROOT
    / "src"
    / "libs"
    / "resume_and_cover_builder"
    / "resume_style"
    / "style_clean_ink.css"
)
TEMPLATE_PATH = PROJECT_ROOT / "resume_templates" / "01-clean-ink.html"


def test_clean_ink_uses_stable_name_and_embedded_typography():
    css = STYLE_PATH.read_text(encoding="utf-8")
    styles = StyleManager().get_styles()

    assert styles["简墨"][0] == "style_clean_ink.css"
    assert "简墨 · Clean Ink" not in styles
    assert 'font-family:"Roboto Embedded","Noto Sans SC",sans-serif' in css
    assert "data:font/woff2;base64," in css
    assert "font-size:9.55pt" in css
    assert "line-height:1.30" in css


def test_clean_ink_example_reuses_production_stylesheet():
    html = TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "简墨 - HTML 简历模板" in html
    assert (
        '../src/libs/resume_and_cover_builder/resume_style/style_clean_ink.css'
        in html
    )
