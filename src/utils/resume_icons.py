"""Make resume contact icons portable and independent of external CDNs."""

import base64
from functools import lru_cache
from pathlib import Path

from bs4 import BeautifulSoup


_ASSET_DIR = (
    Path(__file__).resolve().parents[1]
    / "libs"
    / "resume_and_cover_builder"
    / "assets"
    / "fontawesome"
)


@lru_cache(maxsize=1)
def _embedded_fontawesome_css() -> str:
    solid = base64.b64encode((_ASSET_DIR / "fa-solid-900.woff2").read_bytes()).decode("ascii")
    brands = base64.b64encode((_ASSET_DIR / "fa-brands-400.woff2").read_bytes()).decode("ascii")
    return f"""
@font-face {{ font-family:"Font Awesome 5 Free"; font-style:normal; font-weight:900;
  font-display:block; src:url(data:font/woff2;base64,{solid}) format("woff2"); }}
@font-face {{ font-family:"Font Awesome 5 Brands"; font-style:normal; font-weight:400;
  font-display:block; src:url(data:font/woff2;base64,{brands}) format("woff2"); }}
i.fas {{ font-family:"Font Awesome 5 Free" !important; font-weight:900 !important; }}
i.fab {{ font-family:"Font Awesome 5 Brands" !important; font-weight:400 !important; }}
i.fas,i.fab {{ display:inline-block; width:1em; margin-right:.3em; text-align:center; }}
.contact-info p {{ font-family:"Noto Sans SC",sans-serif; font-weight:700; }}
.fa-map-marker-alt::before {{ content:"\\f3c5"; }}
.fa-phone::before {{ content:"\\f095"; }}
.fa-envelope::before {{ content:"\\f0e0"; }}
.fa-linkedin::before {{ content:"\\f08c"; }}
.fa-github::before {{ content:"\\f09b"; }}
"""


def embed_contact_icons(html: str) -> str:
    """Normalize Font Awesome markup and embed fonts used across the resume."""
    if not html:
        return html

    soup = BeautifulSoup(html, "html.parser")
    has_icon_markup = any(
        class_name.startswith("fa-")
        for item in soup.find_all(class_=True)
        for class_name in (item.get("class") or [])
    )
    if soup.select_one(".contact-info") is None and not has_icon_markup:
        return html

    for item in soup.select(".contact-info p.fas, .contact-info p.fab"):
        classes = list(item.get("class") or [])
        icon_classes = [name for name in classes if name in {"fas", "fab"} or name.startswith("fa-")]
        if not icon_classes:
            continue
        icon = soup.new_tag("i", attrs={"class": icon_classes, "aria-hidden": "true"})
        item.insert(0, icon)
        remaining = [name for name in classes if name not in icon_classes]
        if remaining:
            item["class"] = remaining
        else:
            item.attrs.pop("class", None)

    if soup.head is None:
        html_tag = soup.find("html") or soup.new_tag("html")
        if html_tag.parent is None:
            html_tag.extend(list(soup.contents))
            soup.append(html_tag)
        html_tag.insert(0, soup.new_tag("head"))
    for link in list(soup.head.find_all("link", href=True)):
        if "font-awesome" in str(link.get("href")):
            link.decompose()
    style = soup.find("style", id="buping-embedded-contact-icons")
    if style is None:
        style = soup.new_tag("style", id="buping-embedded-contact-icons")
        soup.head.append(style)
    style.string = _embedded_fontawesome_css()
    return str(soup)
