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


def test_format_boundary_lines():
    lines = format_boundary_observability_lines()
    assert lines[0].startswith("诚实边界观测")
