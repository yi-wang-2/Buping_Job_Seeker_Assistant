from src.libs.ai_engine.harness import enforce_resume_typography


def test_typography_harness_repairs_only_out_of_range_sizes():
    source = """<!DOCTYPE html><html><head><style>
    body { font-size: 6pt; }
    h1 { font-size: 48pt; }
    h2 { font-size: 14pt; }
    .entry-header { font-size: 10pt; }
    .entry-details { font-size: 7pt; }
    </style></head><body>
      <h1>Candidate</h1><h2>Experience</h2>
      <div class="entry-header">Engineer</div>
      <div class="entry-details">2024–2026</div>
      <p>Readable body</p>
    </body></html>"""

    result = enforce_resume_typography(source)

    assert "font-size: 10.066pt" in result.html
    assert "font-size: 32pt" in result.html
    assert "font-size: 14pt" in result.html
    assert "font-size: 10pt" in result.html
    assert "font-size: 8.254pt" in result.html
    assert result.adjusted_count == 3


def test_typography_harness_repairs_inline_body_and_heading_independently():
    source = """<html><body>
      <p><span style="font-size: 30px">Oversized body</span></p>
      <h1><span style="font-size: 20px">Undersized name</span></h1>
      <p style="font-size: 14px">Already readable</p>
    </body></html>"""

    result = enforce_resume_typography(source)

    assert "font-size: 16.617px" in result.html
    assert "font-size: 24.159px" in result.html
    assert "font-size: 14px" in result.html
    assert result.adjusted_count == 2


def test_typography_harness_is_idempotent_and_clamps_font_size_variables():
    source = """<html><head><style>
      :root { --bodyFontSize: .5rem; }
      * { font-size: var(--bodyFontSize); }
    </style></head><body><p>Text</p></body></html>"""

    first = enforce_resume_typography(source)
    second = enforce_resume_typography(first.html)

    assert "--bodyFontSize: 0.839rem" in first.html
    assert first.adjusted_count == 1
    assert second.adjusted_count == 0
    assert second.html == first.html


def test_typography_harness_repairs_legacy_html_font_sizes():
    result = enforce_resume_typography(
        '<html><body><p><font size="7">Huge body text</font></p></body></html>'
    )

    assert 'size="7"' not in result.html
    assert "font-size: 16.617px" in result.html
    assert result.adjusted_count == 1


def test_typography_harness_uses_line_measure_not_one_absolute_size():
    narrow = enforce_resume_typography(
        "<html><head><style>body { max-width: 520px; font-size: 12px; }</style></head><body>Text</body></html>"
    )
    wide = enforce_resume_typography(
        "<html><head><style>body { max-width: 698px; font-size: 12px; }</style></head><body>Text</body></html>"
    )

    assert narrow.adjusted_count == 0  # about 43 full-width characters per line
    assert wide.adjusted_count == 1  # about 58, so text is enlarged
    assert "font-size: 13.422px" in wide.html
    assert narrow.content_width_px == 520
    assert round(wide.content_width_px, 2) == 697.92
