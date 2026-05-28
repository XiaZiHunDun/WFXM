"""Tests for persisted AgentReport storage."""

from butler.report import AgentReport, cache_report, clear_report_cache, get_last_report
from butler.report.store import load_persisted_report, persist_report


def test_persist_and_load_report(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    clear_report_cache("sess-rpt")
    report = AgentReport(
        headline="完成",
        summary="done",
        task_id="task_abc",
        success=True,
    )
    persist_report(report, session_key="sess-rpt", task_id="task_abc")
    loaded = load_persisted_report("sess-rpt")
    assert loaded is not None
    assert loaded.headline == "完成"
    assert loaded.task_id == "task_abc"

    cache_report(report, session_key="sess-rpt")
    assert get_last_report("sess-rpt") is not None
