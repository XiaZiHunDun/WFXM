"""Sprint 11 SEC-11-1: /运行 + /批准运行 加 owner gate

Sprint 11 审计：runtime_commands.py:17-75 handle_runtime_command 缺
owner gate，任何 WECHAT_ALLOWED_USERS 白名单用户（非 Owner）都能调
run_job / approve_and_run 改盘。

修复：
- handle_runtime_command 签名加 platform/external_id/session_key
- /运行 + /批准运行 路径加 is_gateway_owner 守门
- 非 Owner 返回 owner_required_message()
- Owner 正常执行
- message_handler.py:1177 调用点传参

测试：6 个 RED 测试覆盖签名 + Owner/非 Owner 行为 + 两种 cmd。
"""

from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest

from butler.gateway.commands import runtime_handlers as runtime_commands


@pytest.mark.unit
def test_handle_runtime_command_signature_accepts_owner_context():
    """修复后签名应包含 platform/external_id/session_key 参数。"""
    sig = inspect.signature(runtime_commands.handle_runtime_command)
    params = sig.parameters
    for name in ("platform", "external_id", "session_key"):
        assert name in params, (
            f"handle_runtime_command 签名应包含 {name}，实际参数: {list(params.keys())}"
        )


@pytest.mark.unit
def test_approve_run_blocked_for_non_owner():
    """/批准运行 路径：非 Owner 应被 owner_required_message 守门。"""
    from butler.gateway.owner_gate import owner_required_message

    with patch("butler.gateway.commands.runtime_handlers.is_gateway_owner", return_value=False):
        out = runtime_commands.handle_runtime_command(
            orchestrator=None,  # type: ignore[arg-type]
            cmd="/批准运行",
            arg="publish-preflight",
            platform="wechat",
            external_id="non_owner_user",
            session_key="wechat:non_owner_user:proj",
        )
    assert out == owner_required_message(), (
        f"非 Owner /批准运行 应被拒，实际 {out!r}"
    )


@pytest.mark.unit
def test_run_job_blocked_for_non_owner():
    """/运行 路径：非 Owner 应被 owner_required_message 守门。"""
    from butler.gateway.owner_gate import owner_required_message

    with patch("butler.gateway.commands.runtime_handlers.is_gateway_owner", return_value=False):
        out = runtime_commands.handle_runtime_command(
            orchestrator=None,  # type: ignore[arg-type]
            cmd="/运行",
            arg="factory-status-daily",
            platform="wechat",
            external_id="non_owner_user",
            session_key="wechat:non_owner_user:proj",
        )
    assert out == owner_required_message(), (
        f"非 Owner /运行 应被拒，实际 {out!r}"
    )


@pytest.mark.unit
def test_owner_passes_through_approve_run(monkeypatch):
    """Owner 调 /批准运行 应能继续到 run_job 逻辑（不被 gate 拦）。"""
    # 模拟 orchestrator 有 project
    fake_orch = type("O", (), {})()
    fake_pm = type(
        "PM",
        (),
        {"get_current": lambda self, session_key="": type("P", (), {"name": "test_proj"})()},
    )()
    fake_orch.project_manager = fake_pm

    with patch("butler.gateway.commands.runtime_handlers.is_gateway_owner", return_value=True), \
         patch("butler.runtime.service.approve_and_run") as mock_run:
        mock_run.return_value = {"success": True, "summary": "ok"}
        out = runtime_commands.handle_runtime_command(
            orchestrator=fake_orch,  # type: ignore[arg-type]
            cmd="/批准运行",
            arg="publish-preflight",
            platform="wechat",
            external_id="owner_id",
            session_key="wechat:owner_id:proj",
        )
    # Owner 应能调到 approve_and_run（说明未在 gate 阶段被拒）
    assert mock_run.called, "Owner /批准运行 应调到 approve_and_run"
    assert "成功" in out, f"Owner 应收到成功消息，实际 {out!r}"


@pytest.mark.unit
def test_owner_passes_through_run_job(monkeypatch):
    """Owner 调 /运行 应能继续到 run_job 逻辑。"""
    fake_orch = type("O", (), {})()
    fake_pm = type(
        "PM",
        (),
        {"get_current": lambda self, session_key="": type("P", (), {"name": "test_proj"})()},
    )()
    fake_orch.project_manager = fake_pm

    with patch("butler.gateway.commands.runtime_handlers.is_gateway_owner", return_value=True), \
         patch("butler.runtime.service.run_job") as mock_run:
        mock_run.return_value = {"success": True, "summary": "ok"}
        out = runtime_commands.handle_runtime_command(
            orchestrator=fake_orch,  # type: ignore[arg-type]
            cmd="/运行",
            arg="factory-status-daily",
            platform="wechat",
            external_id="owner_id",
            session_key="wechat:owner_id:proj",
        )
    assert mock_run.called, "Owner /运行 应调到 run_job"
    assert "已执行" in out, f"Owner 应收到执行消息，实际 {out!r}"


@pytest.mark.unit
def test_unrelated_command_returns_none_without_owner_check():
    """未识别的 cmd 应返 None（不强制 owner gate，避免误伤其它路径）。"""
    with patch("butler.gateway.commands.runtime_handlers.is_gateway_owner", return_value=False):
        out = runtime_commands.handle_runtime_command(
            orchestrator=None,  # type: ignore[arg-type]
            cmd="/unknown",
            arg="",
            platform="wechat",
            external_id="non_owner",
            session_key="wechat:non_owner:proj",
        )
    assert out is None, f"未识别 cmd 应返 None（交给后续处理），实际 {out!r}"
