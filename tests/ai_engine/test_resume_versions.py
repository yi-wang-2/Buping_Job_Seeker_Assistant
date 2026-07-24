from src.libs.ai_engine.memory import SQLiteMemoryRepository


def test_resume_versions_form_chain_and_deduplicate(tmp_path):
    repository = SQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    first = repository.save_resume_version("name: Alice", language="en")
    duplicate = repository.save_resume_version("name: Alice", language="en")
    second = repository.save_resume_version("name: Alice\nskills: [Python]", language="en")

    assert duplicate["id"] == first["id"]
    assert duplicate["deduplicated"] is True
    versions = repository.list_resume_versions(language="en")
    assert len(versions) == 2
    assert versions[0]["parent_version_id"] == first["id"]
    assert repository.get_resume_version(second["id"])["content"].endswith("[Python]")
