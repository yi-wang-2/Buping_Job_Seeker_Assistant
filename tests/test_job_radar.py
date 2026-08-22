import base64
import json
from pathlib import Path
import sqlite3
import zlib

from backend.services import job_radar_service as radar
from backend.api.endpoints import job_radar as radar_api


COPIED_TABLE = """公司名称\t岗位名称\t工作地点\t招聘类型\t投递链接\t行业\t内推码\n腾讯\t后台开发工程师\t深圳\t27届提前批\thttps://example.com/tencent/backend\t互联网\tREF2027\n\t算法工程师\t北京\t\thttps://example.com/tencent/algorithm\t\t\n某公司\t销售管培生\t上海\t校招\thttps://example.com/sales\t消费\t\n+"""


def _profile_dir(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    (data / "plain_text_resume_zh.yaml").write_text(
        """personal_information:\n  full_name: 测试用户\neducation_details:\n  - education_level: 硕士\nexperience_details:\n  - position: 后台开发工程师\n    skills_acquired: [Python, Linux, Redis]\nprojects:\n  - name: AI项目\n    description: 使用 Python 开发大模型求职助手\n""",
        encoding="utf-8",
    )
    (data / "work_preferences_zh.yaml").write_text(
        """positions: [后台开发工程师, 算法工程师]\nlocations: [深圳, 北京]\ncompany_blacklist: [不投公司]\ntitle_blacklist: [销售]\nlocation_blacklist: []\n""",
        encoding="utf-8",
    )
    return data


def test_parse_copied_tencent_table_inherits_merged_company_fields():
    rows = radar.parse_copied_table(COPIED_TABLE)
    assert len(rows) == 3
    assert rows[0]["company"] == "腾讯"
    assert rows[1]["company"] == "腾讯"
    assert rows[1]["industry"] == "互联网"
    assert rows[1]["recruitment_type"] == "27届提前批"


def test_parse_copied_table_reads_source_updated_at():
    rows = radar.parse_copied_table(
        "公司名称\t岗位名称\t更新时间\t投递链接\n"
        "腾讯\t后端工程师\t2026-08-20 18:30\thttps://example.com/job\n"
    )

    assert rows[0]["source_updated_at"] == "2026-08-20 18:30"


def test_compound_link_header_is_not_misread_as_company_or_role():
    rows = radar.parse_copied_table("公司名称\t岗位名称\t公司招聘链接\n腾讯\t后端工程师\thttps://example.com/job\n")
    assert rows[0]["company"] == "腾讯"
    assert rows[0]["role"] == "后端工程师"
    assert rows[0]["link"] == "https://example.com/job"


def test_import_deduplicates_and_detects_updates(tmp_path):
    db = tmp_path / "radar.sqlite3"
    raw = COPIED_TABLE.encode("utf-8")
    first = radar.import_file("jobs.csv", raw, "https://docs.qq.com/smartsheet/test", db_path=db)
    second = radar.import_file("jobs.csv", raw, "https://docs.qq.com/smartsheet/test", db_path=db)
    changed = COPIED_TABLE.replace("后台开发工程师", "Python后台开发工程师", 1).encode("utf-8")
    third = radar.import_file("jobs.csv", changed, "https://docs.qq.com/smartsheet/test", db_path=db)
    assert first["created"] == 3
    assert second["unchanged"] == 3
    # Role participates in identity, so a renamed role is a newly observed posting.
    assert third["created"] == 1
    assert third["deactivated"] == 1
    assert radar.get_stats(db)["total"] == 3


def test_sync_keeps_source_update_time_separate_from_local_sync_time(tmp_path, monkeypatch):
    db = tmp_path / "radar.sqlite3"
    timestamps = iter((
        "2026-08-20T00:00:00+00:00",
        "2026-08-21T00:00:00+00:00",
        "2026-08-22T00:00:00+00:00",
    ))
    monkeypatch.setattr(radar, "_now", lambda: next(timestamps))
    original = (
        "公司名称\t岗位名称\t更新时间\t投递链接\n"
        "腾讯\t后端工程师\t2026-08-18 09:00\thttps://example.com/job\n"
    ).encode()

    radar.import_file("jobs.csv", original, db_path=db)
    radar.import_file("jobs.csv", original, db_path=db)
    with radar._connect(db) as connection:
        unchanged = dict(connection.execute("SELECT * FROM job_postings").fetchone())

    assert unchanged["source_updated_at"] == "2026-08-18 09:00"
    assert unchanged["first_seen_at"] == "2026-08-20T00:00:00+00:00"
    assert unchanged["last_seen_at"] == "2026-08-21T00:00:00+00:00"
    assert unchanged["updated_at"] == "2026-08-20T00:00:00+00:00"

    source_changed = original.replace(b"2026-08-18 09:00", b"2026-08-22 10:00")
    radar.import_file("jobs.csv", source_changed, db_path=db)
    with radar._connect(db) as connection:
        changed = dict(connection.execute("SELECT * FROM job_postings").fetchone())

    assert changed["source_updated_at"] == "2026-08-22 10:00"
    assert changed["last_seen_at"] == "2026-08-22T00:00:00+00:00"


def test_existing_database_backfills_source_updated_at_from_raw_row(tmp_path):
    db = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(db) as connection:
        connection.execute(
            """CREATE TABLE job_postings (
                id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE, content_hash TEXT NOT NULL,
                source_name TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '', company TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '', industry TEXT NOT NULL DEFAULT '',
                recruitment_type TEXT NOT NULL DEFAULT '', link TEXT NOT NULL DEFAULT '', referral TEXT NOT NULL DEFAULT '',
                deadline TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '', raw_json TEXT NOT NULL DEFAULT '{}',
                first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active')"""
        )
        connection.execute(
            "INSERT INTO job_postings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("job-1", "fingerprint", "hash", "腾讯文档岗位表", "", "腾讯", "后端工程师", "", "", "",
             "", "", "", "", json.dumps({"更新时间": "2026-07-28"}, ensure_ascii=False),
             "local-first", "local-last", "local-updated", "active"),
        )

    with radar._connect(db) as connection:
        row = connection.execute(
            "SELECT source_updated_at, first_seen_at, last_seen_at FROM job_postings"
        ).fetchone()

    assert row["source_updated_at"] == "2026-07-28"
    assert row["first_seen_at"] == "local-first"
    assert row["last_seen_at"] == "local-last"


def test_recommendations_use_resume_and_preferences_without_llm(tmp_path):
    db = tmp_path / "radar.sqlite3"
    data = _profile_dir(tmp_path)
    radar.import_file("jobs.csv", COPIED_TABLE.encode("utf-8"), db_path=db)
    result = radar.list_recommendations(db_path=db, data_dir=data)
    assert result["count"] == 3
    assert result["items"][0]["company"] == "腾讯"
    assert result["items"][0]["score"] > result["items"][-1]["score"]
    sales = next(item for item in result["items"] if "销售" in item["role"])
    assert sales["hard_risks"] == ["岗位名称命中排除词"]
    assert sales["score"] <= 20


def test_direct_sync_uses_read_only_rows(monkeypatch, tmp_path):
    db = tmp_path / "radar.sqlite3"
    monkeypatch.setattr(radar, "read_tencent_sheet", lambda _url: radar.parse_copied_table(COPIED_TABLE))
    result = radar.sync_tencent_sheet("https://docs.qq.com/smartsheet/test", db_path=db)
    assert result["created"] == 3
    assert radar.get_stats(db)["total"] == 3


def test_parse_tencent_read_only_response_uses_field_titles_and_options():
    operations = [[
        {
            "t": 3005,
            "c": {"k3": {"k3": {
                "company_field": {"k30": "企业名称"},
                "industry_field": {"k30": "行业类型", "k9": {"k3": [{"k1": "option_ai", "k2": "人工智能"}]}},
                "link_field": {"k30": "内推链接"},
                "copy_field": {"k30": "整体文案"},
                "updated_field": {"k30": "更新时间"},
            }}},
        },
        {
            "t": 3028,
            "c": {"k2": {"k1": {"row_1": {"k1": {
                "company_field": {"k1": [{"k1": "text", "k2": "示例科技"}]},
                "industry_field": {"k9": ["option_ai"]},
                "link_field": {"k8": [{"k1": "url", "k2": "内推入口", "k3": "https://example.com/jobs"}]},
                "copy_field": {"k1": [{"k1": "text", "k2": "2027 届校园招聘"}]},
                "updated_field": {"k1": [{"k1": "text", "k2": "2026-08-19 12:00"}]},
            }}}}},
        },
    ]]
    packed = base64.b64encode(zlib.compress(json.dumps(operations, ensure_ascii=False).encode("utf-8"))).decode("ascii")
    response = json.dumps({"data": {"initialAttributedText": {"text": [{"smartsheet": packed}]}}})

    rows = radar.parse_tencent_sheet_responses([response])

    assert len(rows) == 1
    assert rows[0]["company"] == "示例科技"
    assert rows[0]["industry"] == "人工智能"
    assert rows[0]["link"] == "https://example.com/jobs"
    assert rows[0]["description"] == "2027 届校园招聘"
    assert rows[0]["source_updated_at"] == "2026-08-19 12:00"


def test_actions_persist_and_remove_company_from_daily_recommendations(tmp_path):
    db = tmp_path / "radar.sqlite3"
    data = _profile_dir(tmp_path)
    radar.import_file("jobs.csv", COPIED_TABLE.encode("utf-8"), db_path=db)

    initial = radar.daily_recommendations(db_path=db, data_dir=data)
    assert len(initial["items"]) == 2  # one recommendation per company
    selected = initial["items"][0]

    state = radar.set_job_action(selected["id"], "favorite", True, db_path=db)
    assert state == {"favorite": True, "not_interested": False, "applied": False}
    favorites = radar.list_recommendations(favorite_only=True, db_path=db, data_dir=data)
    assert [item["id"] for item in favorites["items"]] == [selected["id"]]
    assert radar.get_stats(db)["favorites"] == 1
    refreshed = radar.daily_recommendations(db_path=db, data_dir=data)
    assert all(item["company"] != selected["company"] for item in refreshed["items"])


def test_recommendation_filters_and_tags(tmp_path):
    db = tmp_path / "radar.sqlite3"
    data = _profile_dir(tmp_path)
    table = "公司名称\t岗位名称\t招聘类型\t行业\t岗位描述\t投递链接\n示例科技\tPython开发\t秋招/提前批\t人工智能\t国企正式校招\thttps://example.com/a\n"
    radar.import_file("jobs.csv", table.encode("utf-8"), db_path=db)

    result = radar.list_recommendations(
        company_type="国企/央企", recruitment_type="秋招", db_path=db, data_dir=data,
    )

    assert result["count"] == 1
    assert result["items"][0]["company_type"] == "国企/央企"
    assert result["items"][0]["recruitment_tags"] == ["秋招", "提前批", "正式批"]
    assert result["items"][0]["match_level"] in {"高匹配", "中匹配", "低匹配"}


def test_radar_sync_settings_have_six_am_default_and_persist_source(tmp_path):
    db = tmp_path / "radar.sqlite3"
    defaults = radar.get_radar_settings(db)
    assert defaults["auto_sync"] is True
    assert defaults["auto_sync_time"] == "06:00"
    radar.set_radar_setting("source_url", "https://docs.qq.com/smartsheet/example", db)
    assert radar.get_radar_settings(db)["source_url"].endswith("/example")


def test_explicit_preferences_are_persisted_and_drive_scoring(tmp_path):
    db = tmp_path / "radar.sqlite3"
    data = _profile_dir(tmp_path)
    table = "公司名称\t岗位名称\t行业\t岗位描述\t投递链接\n甲公司\t研发岗位\t人工智能\t大模型研发\thttps://example.com/a\n乙公司\t研发岗位\t消费\t门店业务\thttps://example.com/b\n"
    radar.import_file("jobs.csv", table.encode("utf-8"), db_path=db)
    preferences = radar.get_user_preferences(db, data)
    preferences["industries"] = ["人工智能"]
    preferences["weights"] = {key: (50 if key == "industry" else 0) for key in radar.DEFAULT_SCORE_WEIGHTS}
    radar.save_user_preferences(preferences, db)

    result = radar.list_recommendations(db_path=db, data_dir=data)

    assert radar.get_user_preferences(db, data)["industries"] == ["人工智能"]
    assert result["items"][0]["company"] == "甲公司"
    assert result["items"][0]["score"] == 100


def test_track_confirmation_uses_edited_role_and_base(monkeypatch):
    saved = []
    monkeypatch.setattr(radar_api.job_radar_service, "get_job", lambda _job_id: {
        "company": "原公司", "role": "", "location": "全国", "recruitment_type": "秋招",
        "link": "https://example.com/job", "industry": "人工智能", "description": "原文", "referral": "ABC",
    })
    monkeypatch.setattr(radar_api.job_radar_service, "set_job_action", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(radar_api.job_tracker, "_load_records", lambda: [])
    monkeypatch.setattr(radar_api.job_tracker, "_save_records", lambda records: saved.extend(records))

    result = radar_api.track_job("job-1", radar_api.TrackJobRequest(
        company="确认公司", role="算法工程师", base="北京", recruitment_type="提前批",
        link="https://example.com/job", notes="用户确认备注",
    ))

    assert result["status"] == "added"
    assert saved[0]["company"] == "确认公司"
    assert saved[0]["role"] == "算法工程师"
    assert saved[0]["base"] == "北京"
    assert saved[0]["remark"] == "提前批 / 岗位雷达"


def test_extract_jobs_from_html_reads_jobposting_and_detail_links():
    html = """
    <html><body>
      <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"JobPosting","title":"Python 后端工程师",
       "description":"<p>负责平台服务开发，要求熟悉 Python、Linux 与 Redis。</p>",
       "url":"/jobs/python","jobLocation":{"address":{"addressRegion":"广东省","addressLocality":"深圳市"}}}
      </script>
      <a href="/jobs/algorithm">算法工程师</a><a href="/about">关于我们</a>
    </body></html>
    """

    jobs, links = radar.extract_jobs_from_html(html, "https://careers.example.com/list")

    assert jobs == [{
        "role": "Python 后端工程师",
        "description": "负责平台服务开发，要求熟悉 Python、Linux 与 Redis。",
        "link": "https://careers.example.com/jobs/python",
        "location": "广东省 深圳市",
    }]
    assert links == ["https://careers.example.com/jobs/algorithm"]


def test_extract_jobs_from_html_falls_back_to_rendered_detail_content():
    html = """<html><body><main><h1>算法工程师</h1><section class="job-detail">
    <h1>算法工程师</h1><p>负责推荐算法研发、模型训练和线上效果优化。</p>
    <p>要求熟悉 Python、PyTorch，有扎实的数据结构和机器学习基础，并具备良好沟通能力。</p>
    </section></main></body></html>"""

    jobs, _ = radar.extract_jobs_from_html(html, "https://careers.example.com/jobs/1")

    assert jobs[0]["role"] == "算法工程师"
    assert "PyTorch" in jobs[0]["description"]


def test_extract_jobs_from_html_reads_framework_embedded_state():
    description = "负责 Python 后端服务开发，参与系统设计、测试、上线和日常维护；要求熟悉 Linux、SQL 和常用数据结构。" * 3
    html = f'''<script id="__NEXT_DATA__" type="application/json">{{
      "props": {{"jobs": [{{"jobTitle": "Python 后端工程师", "jobDescription": {json.dumps(description)},
      "detailUrl": "/jobs/42", "city": "深圳"}}]}}
    }}</script>'''

    jobs, _ = radar.extract_jobs_from_html(html, "https://careers.example.com/list")

    assert jobs[0]["role"] == "Python 后端工程师"
    assert jobs[0]["link"] == "https://careers.example.com/jobs/42"
    assert jobs[0]["location"] == "深圳"


def test_harness_filters_navigation_actions_from_job_candidates(monkeypatch):
    monkeypatch.setattr(radar, "_interactive_job_candidates", lambda _driver: [
        {"role": "查看更多", "summary": "查看更多 大模型算法工程师"},
        {"role": "应届生招聘", "summary": "校园招聘入口"},
        {"role": "CVTE2027届秋季校园招聘", "summary": "你的主场"},
        {"role": "广东省·深圳市,湖南省·长沙市", "summary": "工作地点"},
        {"role": "大模型算法工程师", "summary": "北京 算法类"},
    ])

    assert radar._usable_job_candidates(object()) == [
        {"role": "大模型算法工程师", "summary": "北京 算法类"},
    ]


def test_ai_navigation_fallback_uses_context_and_validates_candidate_index(monkeypatch):
    from backend.services import ai_skill_service
    from src.libs.ai_engine.models import LLMResponse, TokenUsage
    from src.libs.ai_engine.providers import LLMGateway

    captured = {}
    monkeypatch.setattr(ai_skill_service, "_resolve_config", lambda *_args: {
        "api_key": "test", "base_url": "", "provider": "openai", "model": "test-model",
    })

    def fake_invoke(_self, request):
        captured["prompt"] = request.messages[0].content
        return LLMResponse(
            content='{"action":"click","index":1,"reason":"进入职位中心"}',
            model="test-model", provider="openai", usage=TokenUsage(100, 20, 120),
        )

    monkeypatch.setattr(LLMGateway, "invoke", fake_invoke)

    class FakeDriver:
        current_url = "https://example.com/campus"
        title = "校园招聘介绍"

        @staticmethod
        def execute_script(_script):
            return "当前是校园招聘介绍页"

    choice, usage = radar._ai_choose_navigation(
        FakeDriver(), ["了解公司", "查看全部职位"], step=2, attempted=["校园招聘"],
    )

    assert choice == "查看全部职位"
    assert usage["total_tokens"] == 120
    assert "当前进度：第 2 层导航" in captured["prompt"]
    assert "已经尝试过" in captured["prompt"]
    assert "只能返回一行 JSON" in captured["prompt"]


def test_doctorate_only_job_is_excluded_for_masters_profile(tmp_path):
    db = tmp_path / "radar.sqlite3"
    data = _profile_dir(tmp_path)
    radar.import_file("jobs.csv", "公司名称\t投递链接\n示例公司\thttps://example.com/jobs\n".encode(), db_path=db)
    parent = radar.list_recommendations(db_path=db, data_dir=data)["items"][0]
    radar._save_linked_jobs(parent["id"], [
        {"role": "大模型算法工程师（博士）", "description": "要求博士学历，负责模型训练", "link": "https://example.com/phd", "location": "北京"},
        {"role": "Python 开发工程师", "description": "硕士及以上，负责后端开发", "link": "https://example.com/master", "location": "北京"},
    ], db)

    cached = radar.list_linked_jobs(parent["id"], db_path=db, data_dir=data)

    assert [item["role"] for item in cached["items"]] == ["Python 开发工程师"]
    assert cached["excluded_count"] == 1


def test_refresh_uses_http_results_without_starting_browser(monkeypatch, tmp_path):
    db = tmp_path / "radar.sqlite3"
    data = _profile_dir(tmp_path)
    radar.import_file("jobs.csv", "公司名称\t投递链接\n示例公司\thttps://example.com/jobs\n".encode(), db_path=db)
    parent = radar.list_recommendations(db_path=db, data_dir=data)["items"][0]
    jobs = [
        {"role": f"Python开发工程师{i}", "description": "负责 Python 后端开发、测试与维护，要求熟悉 Linux 和 SQL。" * 3,
         "link": f"https://example.com/jobs/{i}", "location": "深圳"}
        for i in range(3)
    ]
    monkeypatch.setattr(radar, "_public_job_url", lambda value: value)
    monkeypatch.setattr(radar, "_crawl_jobs_over_http", lambda _url: (
        jobs, {"transport": "http", "pages_scanned": 4, "request_failures": 0,
               "detail_links_seen": 3, "reason": ""},
    ))

    result = radar._recommend_linked_jobs_impl(parent["id"], db_path=db, data_dir=data)

    assert result["status"] == "ok"
    assert result["count"] == 3
    assert result["diagnostics"]["browser_used"] is False
    assert radar.list_linked_jobs(parent["id"], db_path=db, data_dir=data)["count"] == 3


def test_company_score_is_average_of_cached_top_three_jobs(tmp_path):
    db = tmp_path / "radar.sqlite3"
    data = _profile_dir(tmp_path)
    radar.import_file("jobs.csv", "公司名称\t投递链接\n示例公司\thttps://example.com/jobs\n".encode(), db_path=db)
    parent = radar.list_recommendations(db_path=db, data_dir=data)["items"][0]
    radar._save_linked_jobs(parent["id"], [
        {"role": role, "description": description, "link": f"https://example.com/{index}", "location": "深圳"}
        for index, (role, description) in enumerate([
            ("Python 后台开发工程师", "Python Linux Redis 后端开发"),
            ("算法工程师", "Python 大模型算法研发"),
            ("测试工程师", "Python 自动化测试"),
            ("销售专员", "门店销售"),
        ])
    ], db)

    result = radar.list_recommendations(db_path=db, data_dir=data)["items"][0]
    expected = round(sum(item["score"] for item in result["linked_jobs"]) / 3, 1)

    assert result["linked_job_count"] == 4
    assert len(result["linked_jobs"]) == 3
    assert result["score"] == expected
    assert result["reasons"][0] == "企业评分为最相关 3 个岗位的平均分"


def test_auto_match_only_processes_linked_company_below_three_and_respects_cooldown(monkeypatch, tmp_path):
    db = tmp_path / "radar.sqlite3"
    table = "公司名称\t投递链接\n有链接公司\thttps://example.com/jobs\n无链接公司\t备注中没有岗位入口\n"
    radar.import_file("jobs.csv", table.encode(), db_path=db)
    calls = []

    def fake_refresh(job_id, limit=3, db_path=None, data_dir=None):
        calls.append(job_id)
        return {"status": "ok", "count": 3, "items": []}

    monkeypatch.setattr(radar, "recommend_linked_jobs", fake_refresh)

    first = radar.auto_fill_linked_jobs(max_companies=5, cooldown_hours=24, db_path=db, data_dir=tmp_path)
    second = radar.auto_fill_linked_jobs(max_companies=5, cooldown_hours=24, db_path=db, data_dir=tmp_path)

    assert first["processed"] == 1
    assert first["results"][0]["status"] == "complete"
    assert len(calls) == 1
    assert second["processed"] == 0


def test_manual_refresh_returns_cached_jobs_quickly_when_crawler_is_busy(tmp_path):
    db = tmp_path / "radar.sqlite3"
    data = _profile_dir(tmp_path)
    radar.import_file("jobs.csv", "公司名称\t投递链接\n示例公司\thttps://example.com/jobs\n".encode(), db_path=db)
    parent = radar.list_recommendations(db_path=db, data_dir=data)["items"][0]
    radar._save_linked_jobs(parent["id"], [
        {"role": "Python工程师", "description": "Python 后端开发", "link": "https://example.com/1", "location": "深圳"},
    ], db)
    assert radar._DETAIL_CRAWL_LOCK.acquire(timeout=0)
    try:
        started = __import__("time").monotonic()
        result = radar.recommend_linked_jobs(parent["id"], db_path=db, data_dir=data)
        elapsed = __import__("time").monotonic() - started
    finally:
        radar._DETAIL_CRAWL_LOCK.release()

    assert result["status"] == "busy"
    assert result["items"][0]["role"] == "Python工程师"
    assert elapsed < 2.5
