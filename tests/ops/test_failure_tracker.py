"""Runtime consecutive failure tracking."""

from unittest.mock import patch

from butler.runtime.failure_tracker import (
    list_active_streaks,
    record_job_outcome,
)


def test_failure_streak_resets_on_success(tmp_butler_home, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
    monkeypatch.setenv("BUTLER_RUNTIME_FAIL_ALERT_STREAK", "3")

    r1 = record_job_outcome("灵文1号", "factory-status-daily", success=False)
    assert r1["streak"] == 1
    r2 = record_job_outcome("灵文1号", "factory-status-daily", success=False)
    assert r2["streak"] == 2

    record_job_outcome("灵文1号", "factory-status-daily", success=True)
    rows = list_active_streaks()
    assert rows == []

    r3 = record_job_outcome("灵文1号", "factory-status-daily", success=False)
    assert r3["streak"] == 1


def test_failure_alert_at_threshold(tmp_butler_home, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
    monkeypatch.setenv("BUTLER_RUNTIME_FAIL_ALERT_STREAK", "2")

    with patch(
        "butler.runtime.failure_tracker._push_streak_alert", return_value=True
    ) as mock_push:
        record_job_outcome("P", "job-a", success=False)
        r = record_job_outcome("P", "job-a", success=False, audit_path="/tmp/a.json")

    assert r["streak"] == 2
    assert r["alerted"] is True
    mock_push.assert_called_once_with("P", "job-a", 2, "/tmp/a.json")

    # Third failure does not re-alert at streak==3 when threshold is 2 (only exact threshold)
    with patch(
        "butler.runtime.failure_tracker._push_streak_alert", return_value=True
    ) as mock_push2:
        r3 = record_job_outcome("P", "job-a", success=False)
    assert r3["streak"] == 3
    assert r3["alerted"] is False
    mock_push2.assert_not_called()
