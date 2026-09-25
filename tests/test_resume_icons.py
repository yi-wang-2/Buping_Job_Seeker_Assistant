from src.utils.resume_icons import embed_contact_icons
from backend.services.resume_service import refresh_saved_resume_preview_html


def test_contact_icons_are_embedded_and_text_keeps_normal_font():
    source = """<html><head><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.3/css/all.min.css"></head>
    <body><div class="contact-info"><p class="fas fa-phone"><span>13800000000</span></p></div></body></html>"""

    result = embed_contact_icons(source)

    assert "cdnjs.cloudflare.com" not in result
    assert "data:font/woff2;base64," in result
    assert 'font-family:"Noto Sans SC",sans-serif; font-weight:700' in result
    assert '<i aria-hidden="true" class="fas fa-phone"></i>' in result
    assert '<p><i ' in result
    assert "13800000000" in result


def test_contact_icon_embedding_is_idempotent():
    source = '<div class="contact-info"><p class="fas fa-envelope">a@example.com</p></div>'

    once = embed_contact_icons(source)
    twice = embed_contact_icons(once)

    assert twice.count('id="buping-embedded-contact-icons"') == 1
    assert twice.count('class="fas fa-envelope"') == 1


def test_project_github_icon_uses_embedded_brand_font_without_contact_section():
    source = """<html><head></head><body><section id="side-projects">
    <span class="entry-name"><i class="fab fa-github"></i><a href="#">项目名称</a></span>
    </section></body></html>"""

    result = embed_contact_icons(source)

    assert "data:font/woff2;base64," in result
    assert 'i.fab { font-family:"Font Awesome 5 Brands" !important;' in result
    assert '.fa-github::before { content:"\\f09b"; }' in result
    assert '<i class="fab fa-github"></i>' in result


def test_saved_resume_preview_upgrades_legacy_contact_only_icon_scope():
    current = embed_contact_icons(
        """<html><head></head><body><div class="contact-info"><p>联系信息</p></div>
        <section id="side-projects"><i class="fab fa-github"></i>项目名称</section></body></html>"""
    )
    legacy = current.replace(
        'i.fab { font-family:"Font Awesome 5 Brands" !important;',
        '.contact-info .fab { font-family:"Font Awesome 5 Brands" !important;',
    )

    refreshed, style_name, changed = refresh_saved_resume_preview_html(legacy)

    assert style_name == ""
    assert changed is True
    assert 'i.fab { font-family:"Font Awesome 5 Brands" !important;' in refreshed
    assert '.contact-info .fab { font-family:"Font Awesome 5 Brands" !important;' not in refreshed
