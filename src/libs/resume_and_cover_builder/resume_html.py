"""Deterministic post-processing for generated resume HTML."""

import base64
import re
from pathlib import Path


DATA_FOLDER = Path(__file__).resolve().parents[3] / "data_folder"
SUPPORTED_PHOTO_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")

PHOTO_STYLE = """
<style id="resume-photo-style">
  header {
    position: relative !important;
    min-height: 110px !important;
    padding-right: 135px !important;
  }
  .resume-photo-frame {
    position: absolute;
    top: 9px;
    right: 20px;
    width: 69px;
    height: 92px;
    padding: 3px;
    border: 1px solid rgba(51, 51, 51, 0.45);
    border-radius: 4px;
    background: #fff;
    object-fit: cover;
    object-position: center top;
    box-sizing: border-box;
  }
</style>
"""


def add_default_profile_photo(html: str, photo_path: Path | None = None) -> str:
    """Add the bundled profile photo to the first resume header.

    The image is embedded so saved HTML remains portable and Chrome can render
    it after copying the document to a temporary PDF directory.
    """
    if not html or "<header" not in html.lower():
        return html
    if "resume-photo-frame" in html:
        return html

    source = photo_path
    if source is None:
        source = next(
            (DATA_FOLDER / f"resume_photo{ext}" for ext in SUPPORTED_PHOTO_EXTENSIONS
             if (DATA_FOLDER / f"resume_photo{ext}").is_file()),
            None,
        )
    if source is None or not source.is_file():
        return html

    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    mime = "image/jpeg" if source.suffix.lower() in (".jpg", ".jpeg") else f"image/{source.suffix.lower().lstrip('.')}"
    photo = (
        '<img class="resume-photo-frame" alt="profile photo" '
        f'src="data:{mime};base64,{encoded}"/>'
    )
    html = re.sub(r"(<header\b[^>]*>)", rf"\1\n{photo}", html, count=1, flags=re.I)
    if "</head>" in html.lower():
        head_end = html.lower().index("</head>")
        return html[:head_end] + PHOTO_STYLE + html[head_end:]
    return PHOTO_STYLE + html
