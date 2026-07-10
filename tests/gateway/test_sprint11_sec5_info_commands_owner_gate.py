"""Sprint 11 SEC-11-5: /备忘 /通讯录 /记账 /打卡 owner gate

Sprint 11 审计：info_commands.py:34-56 4 个 handler（_cmd_memo / _cmd_contacts /
_cmd_expense / _cmd_habits）无 owner gate；底层数据 owner-scoped
（tools/memo.py:3-8 明确 "owner-level"），任何白名单用户可读 Owner 私人数据。

修复：
- 4 个 handler 顶部加 is_gateway_owner 守门
- 非 Owner 返 owner_required_message()
- Owner 走原有 format_*_for_wechat 逻辑
- CommandContext 已带 platform/external_id/session_key，签名不用改

测试：5 个 RED 测试覆盖 4 命令非 Owner + Owner memo 通过
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.gateway.commands import info_commands


def _ctx(*, cmd: str, arg: str = "", external_id: str = "u", platform: str = "wechat"):
    """Build a minimal CommandContext for handler tests."""
    from butler.gateway.command_registry import CommandContext

    return CommandContext(
        cmd=cmd,
        arg=arg,
        session_key=f"{platform}:{external_id}:proj",
        platform=platform,
        external_id=external_id,
        orchestrator=None,
        session_registry=None,
    )


@pytest.mark.unit
def test_memo_blocked_for_non_owner():
    """/备忘：非 Owner 应被 owner_required_message 守门。"""
    from butler.gateway.owner_gate import owner_required_message

    with patch(
        "butler.gateway.owner_gate.is_gateway_owner", return_value=False
    ):
        out = info_commands._cmd_memo(_ctx(cmd="/备忘", arg="今天买菜", external_id="non_owner"))
    assert out == owner_required_message(), (
        f"非 Owner /备忘 应被拒，实际 {out!r}"
    )


@pytest.mark.unit
def test_contacts_blocked_for_non_owner():
    """/通讯录：非 Owner 应被 owner_required_message 守门。"""
    from butler.gateway.owner_gate import owner_required_message

    with patch(
        "butler.gateway.owner_gate.is_gateway_owner", return_value=False
    ):
        out = info_commands._cmd_contacts(_ctx(cmd="/通讯录", external_id="non_owner"))
    assert out == owner_required_message(), (
        f"非 Owner /通讯录 应被拒，实际 {out!r}"
    )


@pytest.mark.unit
def test_expense_blocked_for_non_owner():
    """/记账：非 Owner 应被 owner_required_message 守门。"""
    from butler.gateway.owner_gate import owner_required_message

    with patch(
        "butler.gateway.owner_gate.is_gateway_owner", return_value=False
    ):
        out = info_commands._cmd_expense(_ctx(cmd="/记账", external_id="non_owner"))
    assert out == owner_required_message(), (
        f"非 Owner /记账 应被拒，实际 {out!r}"
    )


@pytest.mark.unit
def test_habits_blocked_for_non_owner():
    """/打卡：非 Owner 应被 owner_required_message 守门。"""
    from butler.gateway.owner_gate import owner_required_message

    with patch(
        "butler.gateway.owner_gate.is_gateway_owner", return_value=False
    ):
        out = info_commands._cmd_habits(_ctx(cmd="/打卡", external_id="non_owner"))
    assert out == owner_required_message(), (
        f"非 Owner /打卡 应被拒，实际 {out!r}"
    )


@pytest.mark.unit
def test_owner_passes_through_memo():
    """Owner 调 /备忘 应能继续到 format_memos_for_wechat 逻辑。"""
    with patch(
        "butler.gateway.owner_gate.is_gateway_owner", return_value=True
    ), patch("butler.tools.memo.format_memos_for_wechat", return_value="memo list") as mock_fmt:
        out = info_commands._cmd_memo(_ctx(cmd="/备忘", arg="", external_id="owner_id"))
    assert out == "memo list", f"Owner 应能拿到 memo list，实际 {out!r}"
    assert mock_fmt.called, "Owner 应能调到 format_memos_for_wechat"
