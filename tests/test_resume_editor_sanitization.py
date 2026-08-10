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
    <section data-buping-block="true" contenteditable="true"><p>项目一</p><p>项目二</p></section>
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
    assert "撤下" not in cleaned
    assert "data-buping-empty-placeholder" not in cleaned
    assert "该模块中的经历已全部撤下" not in cleaned
    assert "教育背景" in cleaned
    assert "data-buping-library-empty-section" in cleaned
    assert "buping-experience-library-store" in cleaned
    assert "已归档的教育经历" in cleaned
