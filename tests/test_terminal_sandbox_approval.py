"""Approval helpers for terminal sandbox escalation."""

from __future__ import annotations

import json
import time

from butler.tools.terminal_approval import (
    approval_allows_unsandboxed,
    store_approval,
)


def test_store_and_check_unsandboxed_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "butler"))
    store_approval("curl https://example.com", session_key="sk1", unsandboxed=True)
    assert approval_allows_unsandboxed(
        "curl https://example.com",
        session_key="sk1",
    ) is True
    assert approval_allows_unsandboxed(
        "curl https://example.com",
        session_key="sk2",
    ) is False


def test_parse_approve_unsandboxed_command():
    from butler.tools.terminal_approval import parse_approve_unsandboxed_command

    assert parse_approve_unsandboxed_command("/批准沙箱外 npm install") == "npm install"
    assert parse_approve_unsandboxed_command("/approve-unsandboxed pwd") == "pwd"


def test_legacy_exec_approval_migrates_to_approvals_json(tmp_path, monkeypatch):
    import json
    import time as time_mod

    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "butler"))
    monkeypatch.setenv("BUTLER_TERMINAL_REQUIRE_APPROVAL", "1")
    from butler.tools.terminal_approval import (
        _legacy_approval_path,
        argv_fingerprint,
        check_approval,
    )

    cmd = "echo hello"
    fp = argv_fingerprint(cmd, cwd="/tmp")
    legacy = _legacy_approval_path(fp)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        json.dumps(
            {
                "command": cmd,
                "cwd": "/tmp",
                "session_key": "",
                "unsandboxed": False,
                "expires_at": time_mod.time() + 300,
            }
        ),
        encoding="utf-8",
    )
    assert check_approval(cmd, cwd="/tmp") is None
    assert not legacy.is_file()
