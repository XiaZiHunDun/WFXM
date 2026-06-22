"""G1/G2 boundary observability."""

from __future__ import annotations

import json

from butler.ops.boundary_observability import (
    collect_boundary_observations,
    format_boundary_observability_lines,
)
from butler.ops.health_report import HealthReportInput, _shared_diagnostic_lines
from unittest.mock import MagicMock


def test_collect_observations(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    audit = tmp_path / "audit"
    audit.mkdir(parents=True)
    (audit / "eval_feedback.jsonl").write_text(
        json.dumps({"ts": 9_999_999_999.0, "action": "noop"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "metrics").mkdir(exist_ok=True)
    (tmp_path / "metrics" / "cost_baseline.json").write_text(
        json.dumps({"actual_usd": 1.0, "period_note": "test"}),
        encoding="utf-8",
    )

    obs = collect_boundary_observations()
    ids = {o.gap_id for o in obs}
    assert "G1-02" in ids
    assert "G1-04" in ids
    assert "G2-04" in ids
    g102 = next(o for o in obs if o.gap_id == "G1-02")
    assert g102.status == "ok"


def test_format_lines_in_health_report(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    orch = MagicMock()
    orch.project_manager.get_current.return_value = None
    orch._settings = MagicMock()
    inp = HealthReportInput(
        session_key="default",
        health={},
        tool_summary={},
        mem_stats={},
        orchestrator=orch,
    )
    lines = _shared_diagnostic_lines(inp)
    assert any("诚实边界观测" in ln for ln in lines)


def test_g1_04_window_status_counts_in_window(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings
    from butler.ops.boundary_observability import (
        G1_04_WINDOW_START,
        g1_04_observation_window_status,
    )

    reload_butler_settings()
    audit = tmp_path / "audit"
    audit.mkdir(parents=True)
    start_ts, _ = __import__(
        "butler.ops.boundary_observability", fromlist=["_window_epoch_bounds"]
    )._window_epoch_bounds()
    rows = [
        {"ts": start_ts + 100, "action": "adjust_delegate_rescue", "trigger": "b9_live_low_pass"},
        {"ts": start_ts + 200, "action": "adjust_delegate_rescue", "trigger": "b9_live_low_pass"},
        {"ts": start_ts - 10, "action": "old"},
    ]
    (audit / "eval_feedback.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )
    mid = G1_04_WINDOW_START.replace(day=15)
    status = g1_04_observation_window_status(butler_home=tmp_path, today=mid)
    assert status["feedback_in_window"] == 2
    assert status["window_open"] is True
    assert status["feedback_actions_in_window"]["adjust_delegate_rescue"] == 2
    assert status["feedback_b9_eval_only"] is True
    assert status["feedback_evidence_b9_eval"] == 2
    assert status["ot2_closure_ready"] is False


def test_g1_04_production_evidence_enables_ot2_closure(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from datetime import timedelta

    from butler.config import reload_butler_settings
    from butler.ops.boundary_observability import (
        G1_04_WINDOW_END,
        g1_04_observation_window_status,
    )

    reload_butler_settings()
    audit = tmp_path / "audit"
    audit.mkdir(parents=True)
    start_ts, _ = __import__(
        "butler.ops.boundary_observability", fromlist=["_window_epoch_bounds"]
    )._window_epoch_bounds()
    rows = [
        {"ts": start_ts + 100, "action": "adjust_delegate_routing", "trigger": "wechat_eval"},
    ]
    (audit / "eval_feedback.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )
    after = G1_04_WINDOW_END + timedelta(days=1)
    status = g1_04_observation_window_status(butler_home=tmp_path, today=after)
    assert status["window_complete"] is True
    assert status["feedback_evidence_production"] == 1
    assert status["ot2_closure_ready"] is True
    assert status["pipeline_closure_ready"] is True


def test_classify_feedback_evidence():
    from butler.ops.boundary_observability import classify_feedback_evidence

    assert classify_feedback_evidence({"trigger": "b9_live_low_pass"}) == "b9_eval"
    assert classify_feedback_evidence({"trigger": "wechat_hard_feedback"}) == "production"
    assert classify_feedback_evidence({}) == "unknown"


def test_format_boundary_lines():
    lines = format_boundary_observability_lines()
    assert lines[0].startswith("诚实边界观测")
