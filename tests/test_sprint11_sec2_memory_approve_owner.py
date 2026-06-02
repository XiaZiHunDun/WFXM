"""Sprint 11 SEC-11-2: /批准记忆 加 owner gate

Sprint 11 审计：memory_commands.py:86-118 handle_memory_pending_command
/批准记忆 路径缺 owner gate，非 Owner 白名单用户可永久污染项目
MEMORY.md（Pending → Decisions/Notes 等章节，注入到 LLM 长期记忆上下文）。

修复：
- handle_memory_pending_command 签名加 platform/external_id/session_key
- /批准记忆 全部 + 单条 路径加 is_gateway_owner 守门
- 非 Owner 返 owner_required_message()
- Owner 正常批准
- message_handler.py 调用点已传参（SEC-11-1 commit 同时改）

测试：5 个 RED 测试覆盖签名 + /批准记忆 全部 + 单条 + 其它 cmd 仍可用。
"""

from __future__ import annotations

import inspect
from unittest.mock import patch, MagicMock

import pytest

from butler.gateway import memory_commands


@pytest.mark.unit
def test_handle_memory_pending_command_signature_accepts_owner_context():
    """修复后签名应包含 platform/external_id/session_key 参数。"""
    sig = inspect.signature(memory_commands.handle_memory_pending_command)
    params = sig.parameters
    for name in ("platform", "external_id", "session_key"):
        assert name in params, (
            f"handle_memory_pending_command 签名应包含 {name}，"
            f"实际参数: {list(params.keys())}"
        )


@pytest.mark.unit
def test_approve_all_blocked_for_non_owner():
    """/批准记忆 全部：非 Owner 应被 owner_required_message 守门。"""
    from butler.gateway.owner_gate import owner_required_message

    with patch("butler.gateway.memory_commands.is_gateway_owner", return_value=False):
        out = memory_commands.handle_memory_pending_command(
            orchestrator=None,  # type: ignore[arg-type]
            cmd="/批准记忆",
            arg="全部",
            platform="wechat",
            external_id="non_owner",
            session_key="wechat:non_owner:proj",
        )
    assert out == owner_required_message(), (
        f"非 Owner /批准记忆 全部 应被拒，实际 {out!r}"
    )


@pytest.mark.unit
def test_approve_single_blocked_for_non_owner():
    """/批准记忆 <序号>：非 Owner 应被 owner_required_message 守门。"""
    from butler.gateway.owner_gate import owner_required_message

    with patch("butler.gateway.memory_commands.is_gateway_owner", return_value=False):
        out = memory_commands.handle_memory_pending_command(
            orchestrator=None,  # type: ignore[arg-type]
            cmd="/批准记忆",
            arg="1",
            platform="wechat",
            external_id="non_owner",
            session_key="wechat:non_owner:proj",
        )
    assert out == owner_required_message(), (
        f"非 Owner /批准记忆 1 应被拒，实际 {out!r}"
    )


@pytest.mark.unit
def test_owner_passes_through_approve_all():
    """Owner 调 /批准记忆 全部 应能继续到 approve_all 逻辑。"""
    fake_orch = MagicMock()
    fake_orch._reload_project_memory = MagicMock()
    fake_pmem = MagicMock()
    fake_pmem.markdown.list_pending.return_value = [{"target": "Notes", "content": "x"}]
    fake_pmem.markdown.approve_all.return_value = 1
    fake_orch._project_memory = fake_pmem

    with patch("butler.gateway.memory_commands.is_gateway_owner", return_value=True):
        out = memory_commands.handle_memory_pending_command(
            orchestrator=fake_orch,
            cmd="/批准记忆",
            arg="全部",
            platform="wechat",
            external_id="owner",
            session_key="wechat:owner:proj",
        )
    assert "已批准" in out, f"Owner 应能正常批准，实际 {out!r}"
    assert fake_pmem.markdown.approve_all.called, (
        "Owner 应能调到 approve_all"
    )


@pytest.mark.unit
def test_unrelated_command_not_blocked_by_owner_gate():
    """/记忆待审 + /记忆图谱 + /拒绝记忆 是 read-only 路径，不应强制 owner gate。

    注意：SEC-11-2 只覆盖 /批准记忆 写入路径。read-only cmd 不强制
    owner，避免误伤（待审列表本身就要给白名单用户看才能用）。
    """
    fake_orch = MagicMock()
    fake_orch._reload_project_memory = MagicMock()
    fake_pmem = MagicMock()
    fake_pmem.markdown.list_pending.return_value = []
    fake_orch._project_memory = fake_pmem

    with patch("butler.gateway.memory_commands.is_gateway_owner", return_value=False):
        out = memory_commands.handle_memory_pending_command(
            orchestrator=fake_orch,
            cmd="/记忆待审",
            arg="",
            platform="wechat",
            external_id="non_owner",
            session_key="wechat:non_owner:proj",
        )
    # /记忆待审 应正常返回（不应被 owner gate 拦）
    assert "待批准记忆" in out or "没有待批准" in out, (
        f"/记忆待审 应正常返回（不强制 owner），实际 {out!r}"
    )
