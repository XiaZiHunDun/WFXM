"""Tests for publish preflight consistency JSON reader."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "projects"
    / "LingWen1"
    / "novel-factory"
    / "tools"
    / "consistency"
    / "read_latest_report.py"
)


def test_read_latest_report_p0_p1(tmp_path):
    report_dir = tmp_path / "06_意见仓库" / "07_一致性检查"
    report_dir.mkdir(parents=True)
    older = report_dir / "consistency_check_20260101_000000.json"
    newer = report_dir / "consistency_check_20260201_120000.json"
    older.write_text(
        json.dumps({"by_severity": {"P0": 9, "P1": 0, "P2": 0}, "total_issues": 9}),
        encoding="utf-8",
    )
    newer.write_text(
        json.dumps({"by_severity": {"P0": 0, "P1": 2, "P2": 1}, "total_issues": 3}),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    parts = proc.stdout.strip().split()
    assert parts[0] == "0"
    assert parts[1] == "2"
    assert "20260201_120000" in parts[-1]


def test_read_latest_report_missing(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert proc.stdout.strip() == "MISSING"
