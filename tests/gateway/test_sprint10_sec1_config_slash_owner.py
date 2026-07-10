"""Sprint 10 SEC-10-1: /config slash 命令旁路 owner gate（Sprint 9 漏报）

Sprint 9 SEC-9.5 修了 tools/config_tools.py action="set" 路径，但 slash
命令入口 gateway/commands/lifecycle_commands.py:145-163 _cmd_config 未
同步。Prompt 注入 → /config set BUTLER_LOG_LEVEL DEBUG 改运行时配置。

修复：_cmd_config 在 sub=="set" 分支前加 is_gateway_owner 校验，
与同文件 _cmd_revert / _cmd_fork / _cmd_transcript_memory 同款模式。
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from butler.gateway.commands.lifecycle_commands import _cmd_config
from butler.gateway.command_registry import CommandContext


def _make_ctx(arg: str = "", session_key: str = "wechat:u1:p1", external_id: str = "u1") -> CommandContext:
    """构造一个最小的 CommandContext。owner gate 校验需要 platform/external_id/session_key。"""
    return CommandContext(
        cmd="config",
        arg=arg,
        platform="wechat",
        external_id=external_id,
        session_key=session_key,
        orchestrator=None,  # _cmd_config 不调 orchestrator
        session_registry=type("R", (), {"reset": lambda self, sk: None})(),
    )


@pytest.mark.unit
def test_set_subcommand_rejects_non_owner(monkeypatch):
    """非 owner 发 /config set X Y 应被拒（owner_required_message）。"""
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "owner1")
    monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
    ctx = _make_ctx(arg="set BUTLER_LOG_LEVEL DEBUG", session_key="wechat:stranger:p1", external_id="stranger")

    result = _cmd_config(ctx)
    assert result is not None
    # owner_required_message() 返回中含"owner"/"Owner"标识
    assert "owner" in result.lower() or "权限" in result or "仅" in result, (
        f"非 owner 应被拒，实际: {result!r}"
    )


@pytest.mark.unit
def test_set_subcommand_does_not_call_config_set_for_non_owner(monkeypatch):
    """非 owner 不应触发 config_set（即使 path 完全合法）。"""
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "owner1")
    monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
    ctx = _make_ctx(arg="set BUTLER_LOG_LEVEL DEBUG", session_key="wechat:stranger:p1", external_id="stranger")

    with patch("butler.config_service.config_set") as mock_set:
        _cmd_config(ctx)
        mock_set.assert_not_called(), "非 owner 不应调到 config_set"


@pytest.mark.unit
def test_list_subcommand_allows_non_owner(monkeypatch):
    """非 owner 可 /config list（只读）— 不应被 owner gate 拒。"""
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "owner1")
    monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
    ctx = _make_ctx(arg="list", session_key="wechat:stranger:p1")

    result = _cmd_config(ctx)
    assert result is not None
    # 列表输出不应是 owner_required_message
    assert "owner" not in result.lower() or "权限" not in result, (
        f"非 owner 可用 list：{result!r}"
    )


@pytest.mark.unit
def test_get_subcommand_allows_non_owner(monkeypatch):
    """非 owner 可 /config get X（只读）。"""
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "owner1")
    monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
    ctx = _make_ctx(arg="get BUTLER_LOG_LEVEL", session_key="wechat:stranger:p1")

    result = _cmd_config(ctx)
    assert result is not None
    assert "权限" not in result, f"非 owner 可用 get：{result!r}"


@pytest.mark.unit
def test_set_subcommand_allows_owner(monkeypatch):
    """Owner 本身发 /config set X Y 应不被 owner gate 拒。"""
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "u1")
    monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
    ctx = _make_ctx(arg="set BUTLER_LOG_LEVEL DEBUG", session_key="wechat:u1:p1")

    with patch("butler.config_service.config_set") as mock_set:
        mock_set.return_value = type("R", (), {"needs_reset": False, "message": "ok"})()
        result = _cmd_config(ctx)
    # owner 应进到 config_set
    assert mock_set.called, "owner 应调到 config_set"
    # 返回是 config_set.message, 不是 owner_required_message
    assert "权限" not in (result or "")


@pytest.mark.unit
def test_set_invalid_keyvalue_syntax_returns_usage_not_owner_gate(monkeypatch):
    """set sub 缺参数时返回用法提示，不应被 owner gate 抢先。"""
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "u1")
    monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
    ctx = _make_ctx(arg="set ONLY_KEY_NO_VALUE", session_key="wechat:stranger:p1")

    result = _cmd_config(ctx)
    assert result is not None
    # 用法提示而非 owner 拒
    assert "用法" in result or "set" in result.lower()
    assert "权限" not in result and "owner" not in result.lower()


@pytest.mark.unit
def test_owner_gate_check_uses_ctx_platform_external_id_session_key():
    """owner 校验必须用 ctx 透传，handler 不应解构 ctx 字段 (Sprint 18-1).

    Sprint 18-1: 5 个 commands/*.py 改用 command_registry.require_owner 真源.
    _cmd_config 调 require_owner(ctx) 真源, 真源内部从 ctx 拿 platform/external_id/session_key.
    handler 自身只透传 ctx, 不解构. 静态断言: 必须调 require_owner 真源.
    """
    import inspect
    src = inspect.getsource(_cmd_config)
    assert "require_owner" in src, "_cmd_config 必须调 require_owner 真源"
    # handler 应透传 ctx (而非解构 ctx.platform 等字段), 由真源负责解构
    assert "require_owner(ctx)" in src, "_cmd_config 必须透传 ctx 给真源"
