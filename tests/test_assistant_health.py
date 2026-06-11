"""Tests for butler.ops.assistant_health."""

from __future__ import annotations

import json

from butler.ops.assistant_health import (
    AssistantHealthReport,
    collect_assistant_health,
    detect_health_tensions,
    format_assistant_health_lines,
)


def test_detect_memory_ok_dev_low():
    tensions, recs = detect_health_tensions({
        "memory_pass_rate": 0.8,
        "dev_pass_rate": 0.5,
    })
    assert "memory_ok_dev_low" in tensions
    assert recs


def test_detect_delegate_routing_low():
    tensions, _ = detect_health_tensions({"delegate_routing": 0.4})
    assert "delegate_routing_low" in tensions


def test_format_assistant_health_lines():
    report = AssistantHealthReport(
        metrics={"memory_pass_rate": 0.8, "dev_pass_rate": 0.9},
        tensions=[],
    )
    lines = format_assistant_health_lines(report)
    assert any("助手全局健康" in ln for ln in lines)


def test_collect_from_regression_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    audit = tmp_path / "audit"
    audit.mkdir(parents=True)
    (audit / "eval_regression.jsonl").write_text(
        json.dumps({
            "dev_pass_rate": 0.88,
            "mem_pass_rate": 0.75,
            "ts": 1.0,
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "butler.ops.eval_feedback.read_recent_scores",
        lambda **_: [],
    )
    report = collect_assistant_health(lookback_hours=24.0)
    assert report.metrics.get("dev_pass_rate") == 0.88
    assert report.metrics.get("memory_pass_rate") == 0.75
