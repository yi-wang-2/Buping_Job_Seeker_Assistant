from datetime import datetime, timedelta, timezone

from backend.app import followup_schedule_hours, latest_scheduled_time, next_scheduled_time
from backend.api.endpoints import job_tracker


TZ = timezone(timedelta(hours=8))


def test_followup_schedule_has_three_expected_local_times():
    assert followup_schedule_hours(8) == (4, 12, 20)
    assert followup_schedule_hours(6) == (4, 10, 16, 22)
    assert followup_schedule_hours(24) == (4,)


def test_latest_slot_collapses_missed_runs_to_most_recent_time():
    now = datetime(2026, 8, 11, 19, 30, tzinfo=TZ)
    hours = followup_schedule_hours(8)
    assert latest_scheduled_time(now, hours) == datetime(2026, 8, 11, 12, 0, tzinfo=TZ)
    after_evening = datetime(2026, 8, 11, 23, 0, tzinfo=TZ)
    assert latest_scheduled_time(after_evening, hours) == datetime(2026, 8, 11, 20, 0, tzinfo=TZ)


def test_before_first_slot_uses_yesterday_evening_and_next_is_today_four():
    now = datetime(2026, 8, 11, 2, 0, tzinfo=TZ)
    hours = followup_schedule_hours(8)
    assert latest_scheduled_time(now, hours) == datetime(2026, 8, 10, 20, 0, tzinfo=TZ)
    assert next_scheduled_time(now, hours) == datetime(2026, 8, 11, 4, 0, tzinfo=TZ)


def test_next_slot_rolls_to_tomorrow_after_evening_run():
    now = datetime(2026, 8, 11, 20, 1, tzinfo=TZ)
    assert next_scheduled_time(now, followup_schedule_hours(8)) == datetime(2026, 8, 12, 4, 0, tzinfo=TZ)


def test_followup_interval_is_saved_and_invalid_values_are_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(job_tracker, "FOLLOWUP_SETTINGS_FILE", tmp_path / "followup_settings.json")
    assert job_tracker.get_followup_schedule()["interval_hours"] == 8
    assert job_tracker.save_followup_schedule(6)["interval_hours"] == 6
    assert job_tracker.get_followup_schedule()["interval_hours"] == 6
    try:
        job_tracker.save_followup_schedule(3)
    except ValueError as exc:
        assert "4、6、8、12 或 24" in str(exc)
    else:
        raise AssertionError("invalid interval should be rejected")
