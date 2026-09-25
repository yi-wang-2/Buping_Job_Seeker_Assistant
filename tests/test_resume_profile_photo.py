from backend.services import config_service
from src.libs.resume_and_cover_builder import resume_html
from src.libs.resume_and_cover_builder.resume_html import add_default_profile_photo


def test_add_default_profile_photo_embeds_portable_image(tmp_path):
    photo = tmp_path / "photo.png"
    photo.write_bytes(b"test-image")
    html = "<!DOCTYPE html><html><head></head><body><header><h1>Name</h1></header></body></html>"

    result = add_default_profile_photo(html, photo)

    assert result.count("resume-photo-frame") == 2  # CSS selector and image class
    assert "data:image/png;base64,dGVzdC1pbWFnZQ==" in result
    assert "min-height: 110px" in result
    assert "width: 69px" in result
    assert "height: 92px" in result


def test_add_default_profile_photo_is_idempotent(tmp_path):
    photo = tmp_path / "photo.png"
    photo.write_bytes(b"test-image")
    html = "<html><head></head><body><header><h1>Name</h1></header></body></html>"

    once = add_default_profile_photo(html, photo)
    assert add_default_profile_photo(once, photo) == once


def test_saved_photo_replaces_the_snapshot_embedded_in_resume(tmp_path):
    old_photo = tmp_path / "old.png"
    new_photo = tmp_path / "new.png"
    old_photo.write_bytes(b"old-image")
    new_photo.write_bytes(b"new-image")
    html = "<html><head></head><body><header><h1>Name</h1></header></body></html>"

    old_resume = add_default_profile_photo(html, old_photo)
    refreshed = add_default_profile_photo(old_resume, new_photo)

    assert "b2xkLWltYWdl" not in refreshed
    assert "bmV3LWltYWdl" in refreshed
    assert refreshed.count('class="resume-photo-frame"') == 1


def test_deleting_backend_photo_removes_embedded_snapshot_and_spacing(monkeypatch, tmp_path):
    photo = tmp_path / "photo.png"
    photo.write_bytes(b"old-image")
    html = "<html><head></head><body><header><h1>Name</h1></header></body></html>"
    with_photo = add_default_profile_photo(html, photo)
    monkeypatch.setattr(resume_html, "DATA_FOLDER", tmp_path / "empty")

    refreshed = add_default_profile_photo(with_photo)

    assert "resume-photo-frame" not in refreshed
    assert "resume-photo-style" not in refreshed
    assert "padding-right: 135px" not in refreshed


def test_resume_without_uploaded_photo_omits_photo(monkeypatch, tmp_path):
    monkeypatch.setattr(resume_html, "DATA_FOLDER", tmp_path)
    html = "<html><head></head><body><header><h1>Name</h1></header></body></html>"

    assert add_default_profile_photo(html) == html


def test_saved_resume_photo_replaces_previous_format(monkeypatch, tmp_path):
    monkeypatch.setattr(config_service, "DATA_FOLDER", tmp_path)
    (tmp_path / "resume_photo.jpg").write_bytes(b"old")

    saved = config_service.save_resume_photo(b"new", ".png")

    assert saved == tmp_path / "resume_photo.png"
    assert saved.read_bytes() == b"new"
    assert not (tmp_path / "resume_photo.jpg").exists()
