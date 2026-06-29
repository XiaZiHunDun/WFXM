"""Unit tests for TCR strict flip readiness (calendar + rate)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from butler.ops.tcr_strict_readiness import (
    assess_readiness,
    days_until_flip,
    format_summary,
    write_readiness,
)


def _tcr_report(*, ok: bool = True, rate: float = 1.0, passed: int = 51, total: int = 51):
    return {
        "trajectory_compliance_rate": rate,
        "threshold": 0.98,
        "passed": passed,
        "total": total,
        "ok": ok,
    }


@pytest.mark.unit
class TestTcrStrictReadiness:
    def test_days_until_flip_before_and_on_day(self):
        assert days_until_flip(today="2026-06-29", strict_after="2026-07-27") == 28
        assert days_until_flip(today="2026-07-27", strict_after="2026-07-27") == 0
        assert days_until_flip(today="2026-08-01", strict_after="2026-07-27") == 0

    def test_assess_wait_when_calendar_not_ready(self):
        report = assess_readiness(
            tcr_report=_tcr_report(),
            today="2026-06-29",
            strict_after="2026-07-27",
        )
        assert report["status"] == "wait"
        assert report["days_until_flip"] == 28
        assert report["calendar_ready"] is False
        assert "butler-tcr-strict-apply" in report["flip_command"]

    def test_assess_ready_on_flip_day_with_green_tcr(self):
        report = assess_readiness(
            tcr_report=_tcr_report(),
            today="2026-07-27",
            strict_after="2026-07-27",
        )
        assert report["status"] == "ready"
        assert report["calendar_ready"] is True

    def test_assess_fail_when_tcr_below_threshold(self):
        report = assess_readiness(
            tcr_report=_tcr_report(ok=False, rate=0.9, passed=45, total=50),
            today="2026-08-01",
            strict_after="2026-07-27",
        )
        assert report["status"] == "fail"

    def test_format_summary_wait_mentions_apply_script(self):
        report = assess_readiness(
            tcr_report=_tcr_report(),
            today="2026-06-29",
            strict_after="2026-07-27",
        )
        text = format_summary(report)
        assert "WAIT" in text
        assert "butler-tcr-strict-apply" in text

    def test_write_readiness_json(self, tmp_path: Path):
        report = assess_readiness(
            tcr_report=_tcr_report(),
            today="2026-07-27",
            strict_after="2026-07-27",
        )
        out = tmp_path / "tcr-strict-readiness.json"
        write_readiness(report, out)
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["status"] == "ready"
