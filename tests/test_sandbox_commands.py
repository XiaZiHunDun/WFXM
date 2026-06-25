"""Gateway /沙箱 and /cc-bridge commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def owner_ctx(tmp_path):
    from butler.gateway.command_registry import CommandContext

    orch = MagicMock()
    proj = MagicMock()
    proj.workspace = tmp_path
    proj.name = "TestProj"
    orch.project_manager.get_current.return_value = proj
    return CommandContext(
        cmd="/沙箱",
        arg="",
        session_key="wechat:owner:TestProj",
        platform="wechat",
        external_id="owner",
        orchestrator=orch,
        session_registry=MagicMock(),
    )


def test_sandbox_diag(owner_ctx):
    from butler.gateway.commands.sandbox_commands import _cmd_sandbox

    with patch("butler.gateway.commands.sandbox_commands.require_owner", return_value=None):
        text = _cmd_sandbox(owner_ctx)
    assert "终端沙箱" in text
    assert "/批准沙箱外" in text


def test_cc_bridge_requires_enable(owner_ctx):
    from butler.gateway.command_registry import CommandContext
    from butler.gateway.commands.cc_bridge_commands import _cmd_cc_bridge

    ctx = CommandContext(
        cmd="/cc-bridge",
        arg="do something",
        session_key=owner_ctx.session_key,
        platform="wechat",
        external_id="owner",
        orchestrator=owner_ctx.orchestrator,
        session_registry=MagicMock(),
    )
    with patch("butler.gateway.commands.sandbox_commands.require_owner", return_value=None):
        with patch("butler.gateway.commands.cc_bridge_commands.require_owner", return_value=None):
            with patch.dict("os.environ", {"BUTLER_CC_BRIDGE": "0"}, clear=False):
                text = _cmd_cc_bridge(ctx)
    assert "未启用" in text
