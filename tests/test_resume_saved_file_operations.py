from pathlib import Path

from backend.services import resume_service
from src.libs.resume_and_cover_builder.style_manager import StyleManager


def test_rename_saved_resume_moves_pdf_and_html_pair(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(resume_service, "OUTPUT_FOLDER", tmp_path)
    (tmp_path / "old.pdf").write_bytes(b"pdf")
    (tmp_path / "old.html").write_text("<html></html>", encoding="utf-8")

    result = resume_service.rename_saved_resume("old.pdf", "old.html", "研发工程师简历")

    assert result == {
        "pdf_filename": "研发工程师简历.pdf",
        "html_filename": "研发工程师简历.html",
    }
    assert (tmp_path / "研发工程师简历.pdf").read_bytes() == b"pdf"
    assert (tmp_path / "研发工程师简历.html").is_file()
    assert not (tmp_path / "old.pdf").exists()
    assert not (tmp_path / "old.html").exists()


def test_rename_saved_resume_rejects_existing_name(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(resume_service, "OUTPUT_FOLDER", tmp_path)
    for name in ("old.pdf", "old.html", "taken.pdf", "taken.html"):
        (tmp_path / name).write_text(name, encoding="utf-8")

    try:
        resume_service.rename_saved_resume("old.pdf", "old.html", "taken")
    except FileExistsError:
        pass
    else:
        raise AssertionError("Expected an existing target name to be rejected")


def test_overwrite_save_keeps_current_filenames(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(resume_service, "OUTPUT_FOLDER", tmp_path)
    monkeypatch.setattr(resume_service, "render_html_to_pdf_bytes", lambda _html: b"new-pdf")
    (tmp_path / "current.pdf").write_bytes(b"old-pdf")
    (tmp_path / "current.html").write_text("old", encoding="utf-8")

    result = resume_service.convert_html_to_pdf(
        "<html><body>updated</body></html>",
        "ignored-name",
        overwrite_pdf_filename="current.pdf",
        overwrite_html_filename="current.html",
    )

    assert result["pdf_filename"] == "current.pdf"
    assert result["html_filename"] == "current.html"
    assert (tmp_path / "current.pdf").read_bytes() == b"new-pdf"
    assert "updated" in (tmp_path / "current.html").read_text(encoding="utf-8")


def test_switch_template_preserves_body_content_and_module_order(tmp_path: Path, monkeypatch):
    style_path = tmp_path / "new.css"
    style_path.write_text("/*新模板$local*/\nbody{color:navy} h2{border-bottom:2px solid navy}", encoding="utf-8")
    monkeypatch.setattr(StyleManager, "get_styles", lambda _self: {"新模板": ("new.css", "local")})
    monkeypatch.setattr(StyleManager, "get_style_path", lambda _self: style_path)
    source = """<!doctype html><html><head>
    <style>body{color:black}</style><style id="resume-photo-style">img{width:1in}</style>
    </head><body><header><h1>张三</h1></header><main>
    <section id="side-projects"><h2>项目经历</h2><p>项目原文</p></section>
    <section id="education"><h2>教育经历</h2><p>教育原文</p></section>
    </main></body></html>"""

    result = resume_service.switch_resume_template(source, "新模板")

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(result["html"], "html.parser")
    assert soup.body.get_text(" ", strip=True) == "张三 项目经历 项目原文 教育经历 教育原文"
    assert [section.get("id") for section in soup.select("main > section")] == ["side-projects", "education"]
    assert "color:navy" in soup.select_one("#resume-template-style").get_text()
    assert soup.select_one("#resume-photo-style") is not None
