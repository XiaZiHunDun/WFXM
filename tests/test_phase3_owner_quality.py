"""Phase 3: WS-G MCP owner surface + B9 owner quality."""

from __future__ import annotations

import json
import time

from butler.ops.owner_quality_surface import (
    format_b9_owner_line,
    format_delegate_quality_report,
    format_mcp_owner_line,
)


def test_format_mcp_owner_line_disabled(monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_ENABLED", "0")
    line = format_mcp_owner_line("wechat:u:proj")
    assert "关闭" in line


def test_format_b9_owner_line_from_audit(tmp_path, monkeypatch):
    audit = tmp_path / "audit"
    audit.mkdir()
    monkeypatch.setattr(
        "butler.ops.eval_diagnostics._butler_audit_dir",
        lambda: audit,
    )
    record = {
        "ts": time.time(),
        "mode": "oracle",
        "passed": 2,
        "total": 2,
        "pass_rate": 1.0,
        "results": [
            {"task_id": "B9_fix_greet", "passed": True},
            {"task_id": "B9_create_marker", "passed": True},
        ],
    }
    (audit / "b9_benchmark.jsonl").write_text(
        json.dumps(record) + "\n",
        encoding="utf-8",
    )
    line = format_b9_owner_line()
    assert "B9 2/2" in line
    assert "100%" in line or "100" in line


def test_format_delegate_quality_report_includes_b9(tmp_path, monkeypatch):
    audit = tmp_path / "audit"
    audit.mkdir()
    monkeypatch.setattr(
        "butler.ops.eval_diagnostics._butler_audit_dir",
        lambda: audit,
    )
    (audit / "b9_benchmark.jsonl").write_text(
        json.dumps(
            {
                "ts": time.time(),
                "mode": "oracle",
                "passed": 1,
                "total": 2,
                "pass_rate": 0.5,
                "results": [
                    {"task_id": "B9_fix_greet", "passed": True},
                    {"task_id": "B9_create_marker", "passed": False, "error": "verify"},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    text = format_delegate_quality_report()
    assert "委派质量" in text
    assert "B9_create_marker" in text
