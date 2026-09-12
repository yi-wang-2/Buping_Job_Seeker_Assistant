import json

import pytest
from pydantic import ValidationError

from src.libs.ai_engine.knowledge import load_public_knowledge_catalog


def _manifest(**overrides):
    source = {
        "id": "agent-pack", "name": "Agent Pack", "description": "Agent interview knowledge",
        "repository_url": "https://example.com/agent.git", "revision": "a" * 40,
        "source_type": "git", "domain_pack": "ai_agent", "license": "MIT",
        "license_notice": "Review and accept MIT before installation.",
        "license_evidence_path": "README.md", "license_evidence_text": "MIT License",
        "required_paths": ["README.md", "data.json"],
    }
    source.update(overrides)
    return {"schema_version": "1", "sources": [source]}


def test_catalog_loads_only_pinned_https_sources(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(_manifest()), encoding="utf-8")

    catalog = load_public_knowledge_catalog(path)

    assert catalog.get("agent-pack").revision == "a" * 40


@pytest.mark.parametrize("override", [
    {"repository_url": "http://example.com/agent.git"},
    {"revision": "main"},
    {"required_paths": ["../secret.txt"]},
])
def test_catalog_rejects_untrusted_or_unpinned_sources(tmp_path, override):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(_manifest(**override)), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_public_knowledge_catalog(path)
