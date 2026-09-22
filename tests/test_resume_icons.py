from src.utils.resume_icons import embed_contact_icons


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
