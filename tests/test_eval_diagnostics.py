"""G1-05: B9 / O7 eval quality lines for /诊断 and doctor."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from butler.ops.eval_diagnostics import (
    append_b9_audit,
    collect_eval_quality_snapshot,
    format_eval_quality_lines,
)
from butler.ops.health_report import HealthReportInput, _shared_diagnostic_lines


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


class TestEvalDiagnostics:
    def test_format_lines_with_audit_records(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        audit = tmp_path / "audit"
        _write_jsonl(
            audit / "eval_regression.jsonl",
            [{
                "ts": 1_700_000_000.0,
                "passed": True,
                "dev": "8/8",
                "mem": "7/7",
                "dev_pass_rate": 1.0,
                "mem_pass_rate": 1.0,
            }],
        )
        _write_jsonl(
            audit / "b9_benchmark.jsonl",
            [{
                "ts": 1_700_000_100.0,
                "mode": "oracle",
                "passed": 2,
                "total": 2,
                "pass_rate": 1.0,
            }],
        )

        lines = format_eval_quality_lines()
        text = "\n".join(lines)
        assert "开发质量" in text
        assert "Dev B1–B8" in text
        assert "B9 delegate" in text
        assert "8/8" in text
        assert "2/2" in text

    def test_format_lines_empty_audit(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        lines = format_eval_quality_lines()
        text = "\n".join(lines)
        assert "未记录" in text
        assert "butler-eval-regression" in text

    def test_append_b9_audit(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        report = MagicMock()
        report.mode = "oracle"
        report.passed = 2
        report.total = 2
        report.pass_rate = 1.0
        report.results = []
        append_b9_audit(report)
        snap = collect_eval_quality_snapshot()
        assert snap.b9 is not None
        assert snap.b9["passed"] == 2

    def test_health_report_includes_eval_quality(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        _write_jsonl(
            tmp_path / "audit" / "eval_regression.jsonl",
            [{"ts": 1.0, "passed": True, "dev": "8/8", "mem": "7/7",
              "dev_pass_rate": 1.0, "mem_pass_rate": 1.0}],
        )
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
        assert any("开发质量" in ln for ln in lines)
