"""PR-F1: LobeHub P0 — UTF-16 truncate, tool error policy, security_blacklist."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from butler.core.text_truncate import truncate_text, utf16_code_units, utf16_safe_slice
from butler.core.tool_error_policy import (
    ToolErrorKind,
    apply_tool_error_policy,
    classify_tool_error,
    format_tool_error_observation,
)
from butler.permissions import evaluate_security_blacklist


def test_utf16_safe_slice_splits_emoji():
    emoji = "😀" * 3
    assert utf16_code_units(emoji) == 6
    assert utf16_safe_slice(emoji, 4) == "😀" * 2
    assert utf16_code_units(utf16_safe_slice(emoji, 4)) == 4


def test_truncate_text_emoji():
    text = "hello " + "🎉" * 10
    out, truncated = truncate_text(text, 12, suffix="…")
    assert truncated
    assert utf16_code_units(out) <= 12 + 2


def test_classify_retry_vs_stop():
    assert classify_tool_error('{"error":"connection reset"}') == ToolErrorKind.retry
    assert classify_tool_error('{"error":"permission denied","code":"PERMISSION_RULE_DENIED"}') == ToolErrorKind.stop
    assert classify_tool_error("ok output") == ToolErrorKind.ok


def test_apply_tool_error_policy_json_shape():
    raw = apply_tool_error_policy('{"error":"file not found","code":"X"}', tool_name="read_file")
    payload = json.loads(raw)
    assert payload["error_policy"] == "replan"
    assert "错误类型" in payload["error"]
    assert "read_file" in payload["error"] or "换" in payload["error"]


def test_format_tool_error_observation():
    obs = format_tool_error_observation(
        "timeout",
        kind=ToolErrorKind.retry,
        tool_name="terminal",
        code="TOOL_ERROR_RETRY",
    )
    assert "错误类型" in obs
    assert "原因" in obs
    assert "建议下一步" in obs


def test_security_blacklist_param_pattern(tmp_path: Path):
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / ".butler").mkdir()
    (ws / ".butler" / "permissions.yaml").write_text(
        """
security_blacklist:
  - tool: terminal
    param: command
    pattern: "rm -rf /"
    reason: 危险命令
""".strip(),
        encoding="utf-8",
    )
    decision = evaluate_security_blacklist(
        "terminal",
        {"command": "rm -rf /"},
        workspace=ws,
    )
    assert decision is not None
    assert not decision.allowed
    assert decision.permission == "security_blacklist"

    ok = evaluate_security_blacklist(
        "terminal",
        {"command": "ls"},
        workspace=ws,
    )
    assert ok is None
