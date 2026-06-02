"""Sprint 11 SEC-11-6: /评价 加 owner gate

Sprint 11 审计：outcome_commands.py:8-66 handle_outcome_command 全文
0 处 is_gateway_owner；写入 experiments/outcomes.py，污染实验评估日志，
影响后续记忆提炼。

修复：
- 签名加 platform/external_id/session_key 关键字参数
- 顶部加 is_gateway_owner 守门（与 /运行 /批准记忆 对齐）
- 非 Owner 返 owner_required_message()
- Owner 走原有 list_pending / resolve_outcome 逻辑
- message_handler.py 调用点已传参（line 1120）

测试：5 个 RED 测试覆盖 签名 + /评价 list 非 Owner + /评价 写入非 Owner + Owner 通过
"""

from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest

from butler.gateway import outcome_commands


@pytest.mark.unit
def test_handle_outcome_command_signature_accepts_owner_context():
    """修复后签名应包含 platform/external_id/session_key 参数。"""
    sig = inspect.signature(outcome_commands.handle_outcome_command)
    params = sig.parameters
    for name in ("platform", "external_id", "session_key"):
        assert name in params, (
            f"handle_outcome_command 签名应包含 {name}，"
            f"实际参数: {list(params.keys())}"
        )


@pytest.mark.unit
def test_outcome_list_blocked_for_non_owner():
    """/评价 list：非 Owner 应被 owner_required_message 守门。"""
    from butler.gateway.owner_gate import owner_required_message

    with patch(
        "butler.gateway.outcome_commands.is_gateway_owner", return_value=False
    ):
        out = outcome_commands.handle_outcome_command(
            orchestrator=None,  # type: ignore[arg-type]
            arg="list",
            platform="wechat",
            external_id="non_owner",
            session_key="wechat:non_owner:proj",
        )
    assert out == owner_required_message(), (
        f"非 Owner /评价 list 应被拒，实际 {out!r}"
    )


@pytest.mark.unit
def test_outcome_resolve_blocked_for_non_owner():
    """/评价 <row_id> <结果>：非 Owner 应被 owner_required_message 守门。"""
    from butler.gateway.owner_gate import owner_required_message

    with patch(
        "butler.gateway.outcome_commands.is_gateway_owner", return_value=False
    ):
        out = outcome_commands.handle_outcome_command(
            orchestrator=None,  # type: ignore[arg-type]
            arg="row-1 success 反思",
            platform="wechat",
            external_id="non_owner",
            session_key="wechat:non_owner:proj",
        )
    assert out == owner_required_message(), (
        f"非 Owner /评价 <row_id> 应被拒，实际 {out!r}"
    )


@pytest.mark.unit
def test_owner_passes_through_outcome_list(monkeypatch):
    """Owner 调 /评价 list 应能继续到 list_pending 逻辑。"""
    fake_orch = type("O", (), {})()
    fake_pm = type("PM", (), {"get_current": staticmethod(lambda **kw: type("P", (), {"name": "test_proj", "workspace": "/tmp/ws"})())})()
    fake_orch.project_manager = fake_pm

    with patch(
        "butler.gateway.outcome_commands.is_gateway_owner", return_value=True
    ), patch("butler.experiments.outcomes.list_pending", return_value=[]) as mock_list:
        out = outcome_commands.handle_outcome_command(
            orchestrator=fake_orch,  # type: ignore[arg-type]
            arg="list",
            platform="wechat",
            external_id="owner_id",
            session_key="wechat:owner_id:proj",
        )
    assert mock_list.called, "Owner 应能调到 list_pending"
    assert "无 pending" in out, f"Owner 应收到空列表消息，实际 {out!r}"
