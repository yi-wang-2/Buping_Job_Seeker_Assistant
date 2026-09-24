from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.services import job_radar_service
from backend.services.job_radar_query_service import execute_job_radar_query


def _seed(db_path: Path) -> None:
    records = [
        {"company": "甲公司", "role": "Java 开发", "location": "南京", "industry": "软件", "description": "央企校招"},
        {"company": "甲公司", "role": "测试工程师", "location": "南京", "industry": "软件", "description": "央企校招"},
        {"company": "乙公司", "role": "算法工程师", "location": "上海", "industry": "人工智能"},
    ]
    job_radar_service._sync_records(records, "test", "test://jobs", "jobs.json", db_path)


def test_distinct_company_count_is_not_limited_by_result_sample(tmp_path):
    db_path = tmp_path / "radar.sqlite3"
    _seed(db_path)

    result = execute_job_radar_query({
        "operation": "distinct_count", "metric": "companies", "limit": 1,
    }, db_path)

    assert result["value"] == 2
    assert result["scope"] == "database"
    assert result["truncated"] is False


def test_group_by_uses_distinct_companies_and_domain_filters(tmp_path):
    db_path = tmp_path / "radar.sqlite3"
    _seed(db_path)

    result = execute_job_radar_query({
        "operation": "group_by", "metric": "companies", "group_by": "location",
        "filters": {"company_type": ["央企"]},
    }, db_path)

    assert result["rows"] == [{"key": "南京", "count": 1}]
    assert result["filters_applied"]["company_type"] == ["国企/央企"]


def test_search_reports_total_and_truncation(tmp_path):
    db_path = tmp_path / "radar.sqlite3"
    _seed(db_path)

    result = execute_job_radar_query({
        "operation": "search", "filters": {"location": ["南京"]}, "limit": 1,
    }, db_path)

    assert result["total_count"] == 2
    assert result["returned_count"] == 1
    assert result["truncated"] is True


def test_company_search_deduplicates_and_ranks_by_best_matching_job(tmp_path, monkeypatch):
    rows = [
        {"id": "a1", "company": "甲公司", "role": "测试", "score": 40, "match_level": "低匹配"},
        {"id": "a2", "company": "甲公司", "role": "算法", "score": 91, "match_level": "高匹配"},
        {"id": "b1", "company": "乙公司", "role": "开发", "score": 80, "match_level": "高匹配"},
    ]
    monkeypatch.setattr(
        "backend.services.job_radar_query_service._domain_rows", lambda _path: rows,
    )

    result = execute_job_radar_query({
        "operation": "search", "metric": "companies",
        "sort": {"field": "score", "direction": "desc"}, "limit": 2,
    }, tmp_path / "unused.sqlite3")

    assert result["total_count"] == 2
    assert [row["company"] for row in result["rows"]] == ["甲公司", "乙公司"]
    assert result["rows"][0]["score"] == 91
    assert result["rows"][0]["top_role"] == "算法"
    assert result["rows"][0]["job_count"] == 2


def test_provider_style_search_arguments_are_safely_normalized(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.services.job_radar_query_service._domain_rows",
        lambda _path: [{"id": "a", "company": "甲公司", "score": 88, "match_level": "高匹配"}],
    )

    result = execute_job_radar_query({
        "operation": "search", "metric": "jobs", "group_by": "company",
        "sort": "match_score_desc", "limit": 41,
    }, tmp_path / "unused.sqlite3")

    assert result["metric"] == "companies"
    assert result["rows"][0]["company"] == "甲公司"


def test_unknown_fields_and_oversized_limits_are_rejected(tmp_path):
    with pytest.raises(ValidationError):
        execute_job_radar_query({"operation": "count", "sql": "DROP TABLE job_postings"}, tmp_path / "x.db")
    with pytest.raises(ValidationError):
        execute_job_radar_query({"operation": "search", "limit": 51}, tmp_path / "x.db")


def test_filter_values_are_data_and_cannot_modify_the_database(tmp_path):
    db_path = tmp_path / "radar.sqlite3"
    _seed(db_path)

    result = execute_job_radar_query({
        "operation": "search",
        "filters": {"company": ["甲公司'; DROP TABLE job_postings; --"]},
    }, db_path)

    assert result["total_count"] == 0
    assert job_radar_service.get_stats(db_path)["total"] == 3
