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
