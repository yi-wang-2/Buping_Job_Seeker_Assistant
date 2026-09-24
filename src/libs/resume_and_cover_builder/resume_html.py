"""Deterministic post-processing for generated resume HTML."""

import base64
import re
from pathlib import Path


DATA_FOLDER = Path(__file__).resolve().parents[3] / "data_folder"
SUPPORTED_PHOTO_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
UCAS_STYLE_FILE = "style_ucas_academic.css"
UCAS_LOGO = Path(__file__).resolve().parent / "resume_style" / "assets" / "ucas_logo.jpg"


def education_tier_label(education: dict) -> str:
    """Return only school tiers explicitly confirmed in the source data."""
    additional = education.get("additional_info") or {}
    if not isinstance(additional, dict):
        additional = getattr(additional, "model_dump", lambda: {})()
    tiers = []
    if additional.get("is_985") is True:
        tiers.append("985")
    elif additional.get("is_211") is True:
        tiers.append("211")
    if additional.get("is_double_first_class") is True:
        tiers.append("双一流")
    return " · ".join(tiers)

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
    """Add the user's uploaded profile photo to the first resume header.

    The image is embedded so saved HTML remains portable and Chrome can render
    it after copying the document to a temporary PDF directory.
    """
    if not html or "<header" not in html.lower():
        return html
    if re.search(r"<img\b[^>]*\bresume-photo-frame\b[^>]*>", html, flags=re.I):
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
    if 'id="resume-photo-style"' in html or "id='resume-photo-style'" in html:
        return html
    if "</head>" in html.lower():
        head_end = html.lower().index("</head>")
        return html[:head_end] + PHOTO_STYLE + html[head_end:]
    return PHOTO_STYLE + html


def apply_template_branding(html: str, style_file: str) -> str:
    """Embed the institutional mark and optional user photo for the university style.

    Remove the mark when switching to another style. The mark contains no
    person-specific data; a portrait is used only when the user uploaded one.
    """
    from bs4 import BeautifulSoup

    if style_file != UCAS_STYLE_FILE and "ucas-template-logo" not in html:
        return html

    if style_file == UCAS_STYLE_FILE:
        html = add_default_profile_photo(html)

    soup = BeautifulSoup(html, "html.parser")
    for old_logo in soup.select("#ucas-template-logo"):
        old_logo.decompose()
    if style_file != UCAS_STYLE_FILE:
        return str(soup)

    header = soup.find("header")
    if header is None:
        return str(soup)
    logo = soup.new_tag("img")
    logo["id"] = "ucas-template-logo"
    logo["class"] = "ucas-template-logo"
    logo["alt"] = "中国科学院大学校徽"
    logo["src"] = "data:image/jpeg;base64," + base64.b64encode(UCAS_LOGO.read_bytes()).decode("ascii")
    header.insert(0, logo)
    return str(soup)
