import base64
import json
from pathlib import Path
import zlib

from backend.services import job_radar_service as radar
from backend.api.endpoints import job_radar as radar_api


COPIED_TABLE = """公司名称\t岗位名称\t工作地点\t招聘类型\t投递链接\t行业\t内推码\n腾讯\t后台开发工程师\t深圳\t27届提前批\thttps://example.com/tencent/backend\t互联网\tREF2027\n\t算法工程师\t北京\t\thttps://example.com/tencent/algorithm\t\t\n某公司\t销售管培生\t上海\t校招\thttps://example.com/sales\t消费\t\n+"""


def _profile_dir(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    (data / "plain_text_resume_zh.yaml").write_text(
        """personal_information:\n  full_name: 测试用户\nexperience_details:\n  - position: 后台开发工程师\n    skills_acquired: [Python, Linux, Redis]\nprojects:\n  - name: AI项目\n    description: 使用 Python 开发大模型求职助手\n""",
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
            }}},
        },
        {
            "t": 3028,
            "c": {"k2": {"k1": {"row_1": {"k1": {
                "company_field": {"k1": [{"k1": "text", "k2": "示例科技"}]},
                "industry_field": {"k9": ["option_ai"]},
                "link_field": {"k8": [{"k1": "url", "k2": "内推入口", "k3": "https://example.com/jobs"}]},
                "copy_field": {"k1": [{"k1": "text", "k2": "2027 届校园招聘"}]},
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
