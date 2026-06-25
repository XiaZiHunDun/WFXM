"""Sandbox network allowlist mode for bubblewrap."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_wrap_skips_unshare_net_when_allowlist_mode(tmp_path, monkeypatch):
    from butler.tools.terminal_sandbox import (
        NetworkPolicy,
        TerminalSandboxConfig,
        wrap_argv_with_bubblewrap,
    )

    monkeypatch.setenv("BUTLER_TERMINAL_SANDBOX_NETWORK_ALLOWLIST", "1")
    cfg = TerminalSandboxConfig(
        enabled=True,
        sandbox_type="workspace_readwrite",
        network=NetworkPolicy(default="deny", allow=("registry.npmjs.org",)),
    )
    with patch("butler.tools.terminal_sandbox.bubblewrap_path", return_value="/usr/bin/bwrap"):
        argv = wrap_argv_with_bubblewrap(["echo", "hi"], workspace=tmp_path, config=cfg)
    assert "--unshare-net" not in argv


def test_wrap_uses_unshare_net_without_allowlist_mode(tmp_path, monkeypatch):
    from butler.tools.terminal_sandbox import (
        NetworkPolicy,
        TerminalSandboxConfig,
        wrap_argv_with_bubblewrap,
    )

    monkeypatch.delenv("BUTLER_TERMINAL_SANDBOX_NETWORK_ALLOWLIST", raising=False)
    cfg = TerminalSandboxConfig(
        enabled=True,
        network=NetworkPolicy(default="deny", allow=("registry.npmjs.org",)),
    )
    with patch("butler.tools.terminal_sandbox.bubblewrap_path", return_value="/usr/bin/bwrap"):
        argv = wrap_argv_with_bubblewrap(["echo", "hi"], workspace=tmp_path, config=cfg)
    assert "--unshare-net" in argv
