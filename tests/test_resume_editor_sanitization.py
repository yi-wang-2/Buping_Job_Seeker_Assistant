from bs4 import BeautifulSoup

from backend.services.resume_service import _sanitize_edited_resume_html


def test_saved_resume_removes_editor_highlight_and_attributes():
    source = """<!DOCTYPE html><html><head>
    <style id="resume-theme">section { color: black; }</style>
    <style id="buping-editor-style">[contenteditable=true] { outline: 2px solid teal; }</style>
    <style id="buping-layout-controls">body { line-height: 1.4; }</style>
    <style id="buping-page-guide-style">.guide { border-top: 2px dashed red; }</style>
    <style id="buping-print-layout-emulation">html { width: 698px; }</style>
    <style id="buping-viewport-fit">body { transform: scale(.8); }</style>
    </head><body contenteditable="false">
    <section data-buping-block="true" data-buping-module="true" contenteditable="true">
      <div data-buping-module-action="group"><button>模块 ↑</button></div>
      <p>项目一</p><p>项目二</p>
    </section>
    <section id="work-experience">
      <div class="entry" data-buping-removable-entry="true">
        <p>保留的工作经历</p>
        <button data-buping-entry-action="remove" contenteditable="false">撤下</button>
      </div>
    </section>
    <section id="education" data-buping-all-entries-removed="true">
      <h2>教育背景</h2>
      <div data-buping-empty-placeholder="true">该模块中的经历已全部撤下</div>
    </section>
    <div id="buping-experience-library-store" hidden aria-hidden="true">
      <div class="entry" data-buping-library-item="education-1"
           data-buping-library-section-id="education">已归档的教育经历</div>
    </div>
    <div id="buping-page-guides"><div class="guide">page break</div></div>
    <div data-buping-page-break="true">PDF 第 1 页结束</div>
    </body></html>"""

    cleaned = _sanitize_edited_resume_html(source)

    assert "buping-editor-style" not in cleaned
    assert "data-buping-block" not in cleaned
    assert "contenteditable" not in cleaned
    assert "buping-page-guide-style" not in cleaned
    assert "buping-page-guides" not in cleaned
    assert "buping-print-layout-emulation" not in cleaned
    assert "buping-viewport-fit" not in cleaned
    assert "data-buping-page-break" not in cleaned
    assert "buping-layout-controls" in cleaned
    assert "项目一" in cleaned and "项目二" in cleaned
    assert "保留的工作经历" in cleaned
    assert "data-buping-removable-entry" not in cleaned
    assert "data-buping-entry-action" not in cleaned
    assert "data-buping-module-action" not in cleaned
    assert "data-buping-module" not in cleaned
    assert "模块 ↑" not in cleaned
    assert "撤下" not in cleaned
    assert "data-buping-empty-placeholder" not in cleaned
    assert "该模块中的经历已全部撤下" not in cleaned
    assert "教育背景" in cleaned
    assert "data-buping-library-empty-section" in cleaned
    assert "buping-experience-library-store" in cleaned
    assert "已归档的教育经历" in cleaned


def test_saved_resume_normalizes_native_editor_lists():
    source = """<!doctype html><html><body><main><section id="custom">
    <h2>测试模块</h2><p><ul><li>测试项目</li><li>测试项目</li></ul></p>
    </section></main></body></html>"""

    cleaned = _sanitize_edited_resume_html(source)

    soup = BeautifulSoup(cleaned, "html.parser")
    edited_list = soup.select_one("#custom > ul.compact-list")
    assert edited_list is not None
    assert [item.get_text(strip=True) for item in edited_list.select("li")] == ["测试项目", "测试项目"]
    assert soup.select_one("#custom > p > ul") is None


def test_saved_resume_removes_empty_field_editor_hint_but_keeps_time_slot():
    source = """<html><body><section id="side-projects"><div class="entry">
    <span class="entry-year" data-buping-empty-field="时间段（选填）"></span>
    </div></section></body></html>"""

    cleaned = _sanitize_edited_resume_html(source)

    soup = BeautifulSoup(cleaned, "html.parser")
    year = soup.select_one(".entry-year")
    assert year is not None
    assert year.get_text(strip=True) == ""
    assert "data-buping-empty-field" not in year.attrs
