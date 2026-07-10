"""builtin:consistency_weekly_summary — summarize novel-factory consistency JSON.

Read-only collector tests + builtin handler envelope smoke.
"""

from __future__ import annotations

import json
from pathlib import Path

from butler.runtime.builtin_handlers import run_builtin
from butler.tools.consistency_summary_ops import summarize_consistency_report


def _seed_consistency_report(workspace: Path, payload: dict) -> Path:
    """Write a fake consistency_check_report.json under novel-factory/tools/consistency/."""
    target = workspace / "novel-factory" / "tools" / "consistency"
    target.mkdir(parents=True, exist_ok=True)
    path = target / "consistency_check_report.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _full_report() -> dict:
    """Mirror LingWen1 latest report shape: 3 ALIVE_CONFLICT P1 issues."""
    return {
        "started_at": "2026-05-18T13:43:01.107239",
        "chapter_range": "1-360",
        "checks": {
            "naming": {"issues": 0, "details": []},
            "integrity": {"issues": 0, "details": []},
            "duplicates": {"issues": 0, "details": []},
            "character": {
                "issues": 3,
                "details": [
                    ["ALIVE_CONFLICT", 89, "小九", "小九生死状态变化: 存活→死亡"],
                    ["ALIVE_CONFLICT", 111, "苏琳", "苏琳生死状态变化: 存活→死亡"],
                    ["ALIVE_CONFLICT", 253, "小九", "小九生死状态变化: 存活→死亡"],
                ],
            },
            "timeline": {"issues": 0, "details": []},
        },
        "total_issues": 3,
        "by_severity": {"P0": 0, "P1": 3, "P2": 0},
        "completed_at": "2026-05-18T13:51:05.185255",
        "duration_seconds": 484.08,
    }





class TestSummarizeConsistencyReport:
    def test_collector_handles_missing_report(self, tmp_path: Path):
        data = summarize_consistency_report(tmp_path)
        assert data["loaded"] is False
        assert data["error"]
        assert "consistency_check_report.json" in data["path"]
        assert data["verdict"] == "pass"  # default; don't false-positive when report missing

    def test_collector_parses_full_report(self, tmp_path: Path):
        _seed_consistency_report(tmp_path, _full_report())
        data = summarize_consistency_report(tmp_path)
        assert data["loaded"] is True
        assert data["chapter_range"] == "1-360"
        assert data["totals"] == {"P0": 0, "P1": 3, "P2": 0, "total": 3}
        assert data["by_check"]["character"] == 3
        assert data["verdict"] == "warn"  # P1 > 0, P0 = 0
        assert len(data["top_p1"]) == 3
        first = data["top_p1"][0]
        assert first["check"] == "character"
        assert first["issue_type"] == "ALIVE_CONFLICT"
        assert first["chapter"] == 89
        assert first["entity"] == "小九"

    def test_top_p1_capped_at_5(self, tmp_path: Path):
        payload = _full_report()
        # inject 8 character conflicts
        payload["checks"]["character"]["issues"] = 8
        payload["checks"]["character"]["details"] = [
            ["ALIVE_CONFLICT", 100 + i, f"角色{i}", f"角色{i} 状态变化"] for i in range(8)
        ]
        payload["total_issues"] = 8
        payload["by_severity"]["P1"] = 8
        _seed_consistency_report(tmp_path, payload)
        data = summarize_consistency_report(tmp_path)
        assert len(data["top_p1"]) == 5
        assert data["totals"]["total"] == 8

    def test_verdict_mapping(self, tmp_path: Path):
        # P0 > 0 → fail
        p0_payload = _full_report()
        p0_payload["by_severity"] = {"P0": 1, "P1": 0, "P2": 0}
        p0_payload["total_issues"] = 1
        p0_payload["checks"]["naming"] = {"issues": 1, "details": [["BAD_NAME", 5, "x", "y"]]}
        _seed_consistency_report(tmp_path, p0_payload)
        assert summarize_consistency_report(tmp_path)["verdict"] == "fail"

        # P1 > 0, P0 = 0 → warn
        p1_payload = _full_report()
        _seed_consistency_report(tmp_path, p1_payload)
        assert summarize_consistency_report(tmp_path)["verdict"] == "warn"

        # all zero → pass
        clean = _full_report()
        clean["by_severity"] = {"P0": 0, "P1": 0, "P2": 0}
        clean["total_issues"] = 0
        for k in clean["checks"]:
            clean["checks"][k] = {"issues": 0, "details": []}
        _seed_consistency_report(tmp_path, clean)
        assert summarize_consistency_report(tmp_path)["verdict"] == "pass"

    def test_collector_handles_corrupt_json(self, tmp_path: Path):
        target = tmp_path / "novel-factory" / "tools" / "consistency"
        target.mkdir(parents=True, exist_ok=True)
        (target / "consistency_check_report.json").write_text("not-json{", encoding="utf-8")
        data = summarize_consistency_report(tmp_path)
        assert data["loaded"] is False
        assert data["error"]


class TestBuiltinConsistencyWeeklySummary:
    def test_builtin_handler_returns_envelope(self, tmp_path: Path):
        _seed_consistency_report(tmp_path, _full_report())
        result = run_builtin("builtin:consistency_weekly_summary", tmp_path)
        assert result["success"] is True
        assert result["stderr"] == ""
        # summary 应含 counts 与 verdict
        assert "P0=0" in result["summary"]
        assert "P1=3" in result["summary"]
        assert "1-360" in result["summary"]
        assert "warn" in result["summary"] or "有条件" in result["summary"]

    def test_builtin_handler_reports_missing_report(self, tmp_path: Path):
        # no JSON file
        result = run_builtin("builtin:consistency_weekly_summary", tmp_path)
        assert result["success"] is False
        assert "未找到" in result["summary"] or "missing" in result["summary"].lower()
        assert result["stderr"]
