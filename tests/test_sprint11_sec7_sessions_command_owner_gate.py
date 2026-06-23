"""Sprint 11 SEC-11-7: /会话 加 owner gate

Sprint 11 审计：sessions_commands.py:9-38 list_sessions() 返回全量
session_key（含 chat_id），无 owner gate → 信息泄露（任何白名单用户
能拿到 Owner 与其它用户的 chat_id 列表）。

修复：
- 签名加 platform/external_id 关键字参数
- 顶部加 is_gateway_owner 守门
- 非 Owner 返 owner_required_message()
- Owner 走原有 list_sessions 逻辑
- message_handler.py:1109 调用点已传参

测试：4 个 RED 测试覆盖 签名 + /会话 非 Owner 路径 + Owner 通过
"""

from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest

from butler.gateway import sessions_commands


@pytest.mark.unit
def test_handle_sessions_command_signature_accepts_owner_context():
    """修复后签名应包含 platform/external_id 参数（session_key 已有）。"""
    sig = inspect.signature(sessions_commands.handle_sessions_command)
    params = sig.parameters
    for name in ("platform", "external_id"):
        assert name in params, (
            f"handle_sessions_command 签名应包含 {name}，"
            f"实际参数: {list(params.keys())}"
        )


@pytest.mark.unit
def test_sessions_list_blocked_for_non_owner():
    """/会话：非 Owner 应被 owner_required_message 守门。"""
    from butler.gateway.owner_gate import owner_required_message

    with patch(
        "butler.gateway.commands.sessions_handlers.is_gateway_owner", return_value=False
    ):
        out = sessions_commands.handle_sessions_command(
            orchestrator=None,  # type: ignore[arg-type]
            arg="",
            platform="wechat",
            external_id="non_owner",
            session_key="wechat:non_owner:proj",
        )
    assert out == owner_required_message(), (
        f"非 Owner /会话 应被拒，实际 {out!r}"
    )


@pytest.mark.unit
def test_sessions_search_blocked_for_non_owner():
    """/会话 <关键词>：非 Owner 应被 owner_required_message 守门。"""
    from butler.gateway.owner_gate import owner_required_message

    with patch(
        "butler.gateway.commands.sessions_handlers.is_gateway_owner", return_value=False
    ):
        out = sessions_commands.handle_sessions_command(
            orchestrator=None,  # type: ignore[arg-type]
            arg="proj-2026",
            platform="wechat",
            external_id="non_owner",
            session_key="wechat:non_owner:proj",
        )
    assert out == owner_required_message(), (
        f"非 Owner /会话 <搜索> 应被拒，实际 {out!r}"
    )


@pytest.mark.unit
def test_owner_passes_through_sessions_list(monkeypatch):
    """Owner 调 /会话 应能继续到 list_sessions 逻辑。"""
    fake_orch = type("O", (), {})()
    fake_pm = type("PM", (), {"get_current": staticmethod(lambda **kw: type("P", (), {"name": "test_proj"})())})()
    fake_orch.project_manager = fake_pm

    with patch(
        "butler.gateway.commands.sessions_handlers.is_gateway_owner", return_value=True
    ), patch("butler.cli.sessions_cli.list_sessions", return_value=[]) as mock_list:
        out = sessions_commands.handle_sessions_command(
            orchestrator=fake_orch,  # type: ignore[arg-type]
            arg="",
            platform="wechat",
            external_id="owner_id",
            session_key="wechat:owner_id:proj",
        )
    assert mock_list.called, "Owner 应能调到 list_sessions"
    assert "暂无" in out, f"Owner 空结果应返 '暂无'，实际 {out!r}"
