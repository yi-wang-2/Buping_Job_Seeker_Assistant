from src.libs.ai_engine.optimization import changed_sections, section_fingerprints


def test_changed_sections_only_reports_modified_parts():
    before = section_fingerprints({"education": "A", "experience": "B"})
    after = section_fingerprints({"education": "A", "experience": "C"})

    assert changed_sections(before, after) == {"experience"}

