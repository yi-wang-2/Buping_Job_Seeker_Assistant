from pathlib import Path

from backend.services import resume_service


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
