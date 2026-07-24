from src.libs.ai_engine.memory import SQLiteMemoryRepository


def test_job_description_archive_deduplicates_and_refreshes(tmp_path):
    repository = SQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    first = repository.archive_job_description(
        "招聘 Python 工程师",
        {"role": "Python 工程师", "required_skills": ["Python"]},
        role="Python 工程师",
    )
    second = repository.archive_job_description(
        "招聘 Python 工程师",
        {"role": "高级 Python 工程师", "required_skills": ["Python"]},
        role="高级 Python 工程师",
    )

    assert first["id"] == second["id"]
    assert second["deduplicated"] is True
    items = repository.list_job_descriptions()
    assert len(items) == 1
    assert items[0]["role"] == "高级 Python 工程师"
