import pytest
from types import SimpleNamespace
from bs4 import BeautifulSoup

from backend.services.resume_service import (
    apply_target_page_layout,
    build_preserved_resume_context,
    condense_resume_html_with_llm,
    fit_resume_to_target_pages,
    get_generation_progress,
    merge_regenerated_resume_html,
    validate_regenerate_targets,
    update_generation_progress,
)
from src.libs.resume_and_cover_builder.resume_generator import ResumeGenerator


BASE_HTML = """<!DOCTYPE html><html><head><style id="base-style">body{color:black}</style></head><body>
<header><h1>保留姓名</h1></header>
<section id="education"><div class="entry"><span class="entry-name">保留学校</span></div></section>
<section id="work-experience">
  <div class="entry"><span class="entry-name">保留公司 A</span><li>保留工作 A</li></div>
  <div class="entry"><span class="entry-name">保留公司 B</span><li>旧工作 B</li></div>
</section>
<section id="side-projects"><div class="entry"><span class="entry-name">旧项目</span></div></section>
</body></html>"""


GENERATED_HTML = """<!DOCTYPE html><html><head><style id="new-style">body{color:red}</style></head><body>
<header><h1>新姓名</h1></header>
<section id="education"><div class="entry"><span class="entry-name">新学校</span></div></section>
<section id="work-experience">
  <div class="entry"><span class="entry-name">新公司 A</span><li>新工作 A</li></div>
  <div class="entry"><span class="entry-name">新公司 B</span><li>新工作 B</li></div>
</section>
<section id="side-projects"><div class="entry"><span class="entry-name">新项目</span></div></section>
</body></html>"""


def test_partial_regeneration_replaces_only_selected_section_and_entry():
    result = merge_regenerated_resume_html(
        BASE_HTML,
        GENERATED_HTML,
        ["entry:work-experience:1", "section:side-projects"],
    )
    soup = BeautifulSoup(result, "html.parser")

    assert soup.find(id="base-style") is not None
    assert soup.find(id="new-style") is None
    assert soup.header.get_text(" ", strip=True) == "保留姓名"
    assert soup.find(id="education").get_text(" ", strip=True) == "保留学校"
    work_entries = soup.select("#work-experience .entry")
    assert "保留公司 A" in work_entries[0].get_text(" ", strip=True)
    assert "新公司 B" in work_entries[1].get_text(" ", strip=True)
    assert "旧工作 B" not in work_entries[1].get_text(" ", strip=True)
    assert "新项目" in soup.find(id="side-projects").get_text(" ", strip=True)


def test_selecting_parent_section_supersedes_child_entry_target():
    result = merge_regenerated_resume_html(
        BASE_HTML,
        GENERATED_HTML,
        ["section:work-experience", "entry:work-experience:0"],
    )

    assert "新公司 A" in result and "新公司 B" in result
    assert "保留公司 A" not in result and "保留公司 B" not in result


def test_partial_regeneration_requires_supported_nonempty_targets():
    with pytest.raises(ValueError, match="at least one"):
        validate_regenerate_targets([])
    with pytest.raises(ValueError, match="Unsupported resume section"):
        validate_regenerate_targets(["section:unknown"])
    with pytest.raises(ValueError, match="Unsupported resume entry"):
        validate_regenerate_targets(["entry:achievements:0"])


def test_partial_regeneration_rejects_missing_entry_index():
    with pytest.raises(ValueError, match="no longer exists"):
        merge_regenerated_resume_html(
            BASE_HTML,
            GENERATED_HTML,
            ["entry:work-experience:9"],
        )


def test_preserved_content_and_format_are_built_as_llm_context():
    context = build_preserved_resume_context(
        BASE_HTML.replace("</body>", "<script>ignore me</script></body>"),
        ["entry:work-experience:1", "section:side-projects"],
    )

    assert "<FORMAT_REFERENCE>" in context
    assert 'id="base-style"' in context
    assert "<LOCKED_CONTENT>" in context
    assert "保留姓名" in context
    assert "保留公司 A" in context
    assert "保留公司 B" not in context
    assert "旧项目" not in context
    assert "ignore me" not in context


def test_preserved_context_reserves_space_for_locked_content_when_css_is_large():
    base_html = (
        "<html><head><style>" + (".resume{color:#123456}" * 3000) + "</style></head><body>"
        '<section id="education"><div class="entry">REGENERATE</div></section>'
        '<section id="work-experience"><div class="entry">LOCKED-FACT</div></section>'
        "</body></html>"
    )

    context = build_preserved_resume_context(base_html, ["section:education"], max_chars=40_000)

    assert len(context) <= 40_000
    assert "<style>" in context
    assert "LOCKED-FACT" in context
    assert "REGENERATE" not in context


def test_target_page_layout_preserves_content_and_fits_dense_one_page(monkeypatch):
    monkeypatch.setattr("backend.services.resume_service.count_pdf_pages", lambda data: int(data.decode()))

    def renderer(html: str) -> bytes:
        spacing = float(html.split("--buping-spacing-factor:", 1)[1].split(";", 1)[0].strip())
        return b"1" if spacing <= 0.75 else b"2"

    fitted_html, pdf, pages, scale, warnings = fit_resume_to_target_pages(
        "<html><head></head><body><section>KEEP-CONTENT</section></body></html>",
        b"2",
        1,
        renderer=renderer,
    )

    assert pages == 1 and pdf == b"1"
    assert scale <= 0.75
    assert "KEEP-CONTENT" in fitted_html
    assert "target_one_page_content_dense" in warnings


def test_target_page_layout_flattens_nested_documents_and_scales_only_root_body():
    nested = """<!DOCTYPE html><html><head><style>body{margin:0 auto}</style></head><body>
    <!DOCTYPE html><html><head><style>.resume{color:black}</style></head>
    <body><main class="resume">KEEP-CONTENT</main></body></html>
    </body></html>"""

    fitted_html = apply_target_page_layout(nested, 0.75)
    soup = BeautifulSoup(fitted_html, "html.parser")

    assert len(soup.find_all("html")) == 1
    assert len(soup.find_all("body")) == 1
    assert soup.select_one("main.resume").get_text(strip=True) == "KEEP-CONTENT"
    layout_css = soup.find(id="buping-target-page-layout").get_text()
    controls_css = soup.find(id="buping-layout-controls").get_text()
    assert ":root > body" in layout_css
    assert "html body" not in layout_css
    assert "zoom:" not in layout_css
    assert "max-width: 700px" in layout_css
    assert "margin-left: auto" in layout_css
    assert ".compact-list" in controls_css
    assert soup.find(id="buping-layout-controls")["data-line-height"] == "1.2650"
    assert soup.find(id="buping-layout-controls")["data-module-spacing"] == "6.5000"


def test_target_page_layout_expands_short_content_to_two_pages(monkeypatch):
    monkeypatch.setattr("backend.services.resume_service.count_pdf_pages", lambda data: int(data.decode()))

    def renderer(html: str) -> bytes:
        spacing = float(html.split("--buping-spacing-factor:", 1)[1].split(";", 1)[0].strip())
        if spacing < 1.15:
            return b"1"
        return b"2"

    fitted_html, pdf, pages, scale, warnings = fit_resume_to_target_pages(
        "<html><head></head><body><section>SHORT-CONTENT</section></body></html>",
        b"1",
        2,
        renderer=renderer,
    )

    assert pages == 2 and pdf == b"2"
    assert 1.15 <= scale <= 1.35
    assert "SHORT-CONTENT" in fitted_html
    assert "target_two_pages_content_short" in warnings


def test_target_page_layout_uses_content_compactor_only_after_spacing_limit(monkeypatch):
    monkeypatch.setattr("backend.services.resume_service.count_pdf_pages", lambda data: int(data.decode()))
    calls: list[str] = []

    def renderer(html: str) -> bytes:
        return b"1" if "CONDENSED" in html else b"2"

    ratios: list[float] = []

    def compact(html: str, target_ratio: float) -> tuple[str, bool]:
        calls.append(html)
        ratios.append(target_ratio)
        return html.replace("VERBOSE", "CONDENSED"), True

    fitted_html, _, pages, _, warnings = fit_resume_to_target_pages(
        "<html><head></head><body><section>VERBOSE</section></body></html>",
        b"2",
        1,
        renderer=renderer,
        content_compactor=compact,
    )

    assert len(calls) == 1
    assert ratios == [pytest.approx(0.41)]
    assert pages == 1
    assert "CONDENSED" in fitted_html
    assert "content_completeness_impacted" in warnings


def test_target_page_layout_repeats_compaction_until_real_pdf_fits(monkeypatch):
    monkeypatch.setattr("backend.services.resume_service.count_pdf_pages", lambda data: int(data.decode()))
    rounds: list[float] = []

    def renderer(html: str) -> bytes:
        return b"1" if ">X<" in html else b"2"

    def compact(html: str, target_ratio: float) -> tuple[str, bool]:
        rounds.append(target_ratio)
        if "SHORT-ONE" in html:
            return html.replace("SHORT-ONE", "X"), False
        return html.replace("VERBOSE-CONTENT-LONG", "SHORT-ONE"), False

    fitted_html, _, pages, _, _ = fit_resume_to_target_pages(
        "<html><head></head><body><main>VERBOSE-CONTENT-LONG</main></body></html>",
        b"2",
        1,
        renderer=renderer,
        content_compactor=compact,
    )

    assert pages == 1
    assert ">X<" in fitted_html
    assert len(rounds) == 2


def test_llm_compactor_sends_only_main_content_not_photo_or_header(monkeypatch):
    captured: list[str] = []

    class FakeClient:
        def invoke(self, messages):
            captured.append(messages[0]["content"])
            return SimpleNamespace(
                content='<section id="education"><div class="entry"><ul><li>SHORT</li></ul></div></section>'
            )

    monkeypatch.setattr(
        "src.libs.resume_and_cover_builder.llm.llm_generate_resume._create_gateway_chat_model",
        lambda *_args, **_kwargs: FakeClient(),
    )
    monkeypatch.setattr(
        "src.libs.ai_engine.harness.protect_hard_facts_in_place",
        lambda sections, _resume, language="zh": SimpleNamespace(sections=sections, violations=()),
    )
    source = """<html><head></head><body>
      <header><img src="data:image/png;base64,VERY-LARGE-PHOTO"/><h1>LOCKED NAME</h1></header>
      <main><section id="education"><div class="entry"><ul><li>VERY LONG DESCRIPTION</li></ul></div></section></main>
    </body></html>"""

    result, _ = condense_resume_html_with_llm(
        source, object(), "test-key", target_pages=1, target_text_ratio=0.4
    )

    assert len(captured) == 1
    assert "VERY LONG DESCRIPTION" in captured[0]
    assert "VERY-LARGE-PHOTO" not in captured[0]
    assert "LOCKED NAME" not in captured[0]
    assert "40%-48%" in captured[0]
    assert "LOCKED NAME" in result
    assert "SHORT" in result


def test_generation_progress_keeps_real_milestone_history():
    request_id = "test-progress-milestones"
    update_generation_progress(request_id, 0, "queued", "accepted")
    update_generation_progress(request_id, 30, "llm_candidates", "candidate generation started")
    update_generation_progress(request_id, 54, "llm_candidates", "candidate 3/3 completed")
    update_generation_progress(request_id, 100, "completed", "done", status="completed")

    progress = get_generation_progress(request_id)

    assert progress is not None
    assert progress["progress"] == 100
    assert progress["status"] == "completed"
    assert [event["progress"] for event in progress["events"]] == [0, 30, 54, 100]


def test_resume_generator_assembles_exactly_one_html_document(tmp_path):
    class FakeAnswerer:
        def set_resume(self, _resume): pass
        def set_regeneration_context(self, _context, _targets): pass
        def set_target_pages(self, _pages): pass
        def set_progress_callback(self, _callback): pass
        def generate_html_resume(self):
            return "<header><h1>NAME</h1></header><main><section id='education'>EDU</section></main>"

    style_path = tmp_path / "resume.css"
    style_path.write_text("body{font-size:10pt}", encoding="utf-8")
    generator = ResumeGenerator()
    generator.set_resume_object(object())

    result = generator._create_resume(FakeAnswerer(), style_path)
    soup = BeautifulSoup(result, "html.parser")

    assert len(soup.find_all("html")) == 1
    assert len(soup.find_all("body")) == 1
    assert soup.select_one("body > header h1").get_text(strip=True) == "NAME"
