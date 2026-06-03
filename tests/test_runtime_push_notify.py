"""Runtime WeChat push cooldown."""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest

from butler.runtime import notify


@pytest.fixture
def butler_home_push(tmp_path, monkeypatch):
    bh = tmp_path / "bh"
    bh.mkdir()
    monkeypatch.setenv("BUTLER_HOME", str(bh))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    return bh


def test_push_cooldown_waits(butler_home_push, monkeypatch):
    monkeypatch.setenv("BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS", "2")
    notify._write_last_push_monotonic(time.monotonic() - 0.5)

    slept = []
    monkeypatch.setattr(notify.time, "sleep", lambda s: slept.append(s))
    wait = notify._wait_push_cooldown()

    assert wait > 0
    assert slept and slept[0] > 0


def test_push_records_timestamp_on_success(butler_home_push, monkeypatch):
    monkeypatch.setenv("BUTLER_RUNTIME_PUSH", "1")
    monkeypatch.setenv("BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("WECHAT_TOKEN", "t")
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "user1")

    async def _fake_send(**_kwargs):
        return {}

    with patch(
        "butler.gateway.platforms.wechat_ilink.send_wechat_direct",
        side_effect=_fake_send,
    ):
        ok = notify.push_runtime_message("t", "body")

    assert ok is True
    path = butler_home_push / "runtime" / "last_push_at.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "monotonic" in data


def test_push_uses_gateway_allowlist_fallback(butler_home_push, monkeypatch):
    monkeypatch.setenv("BUTLER_RUNTIME_PUSH", "1")
    monkeypatch.setenv("BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("WECHAT_TOKEN", "t")
    monkeypatch.delenv("BUTLER_OWNER_WECHAT_ID", raising=False)
    monkeypatch.delenv("WECHAT_ALLOWED_USERS", raising=False)
    monkeypatch.setenv("BUTLER_GATEWAY_ALLOWLIST", "legacy1,legacy2")

    seen: dict[str, str] = {}

    async def _fake_send(**kwargs):
        seen["chat_id"] = kwargs["chat_id"]
        return {}

    with patch(
        "butler.gateway.platforms.wechat_ilink.send_wechat_direct",
        side_effect=_fake_send,
    ):
        ok = notify.push_runtime_message("t", "body")

    assert ok is True
    assert seen["chat_id"] == "legacy1"


# ── Sprint 16 REL-11-3: push_runtime_message 不应在运行中的 event loop 中崩溃 ──


class TestPushFromRunningEventLoop:
    """bug: butler/runtime/notify.py:130 ``asyncio.run(send_wechat_direct(...))``

    ``asyncio.run`` 试图创建新 event loop, 但当前线程已有一个在跑
    (如 MCP tool handler 内部), 抛 ``RuntimeError: asyncio.run() cannot be
    called from a running event loop``。

    修复: 改用 butler.mcp.async_runner.run_mcp_async, 该 runner 维护独立线程 +
    event loop, 安全从任何 sync/async 上下文调用。
    """

    def test_push_works_from_inside_running_event_loop(
        self, butler_home_push, monkeypatch,
    ):
        """从正在运行的 event loop 内同步调 push_runtime_message 不应崩。"""
        import asyncio

        monkeypatch.setenv("BUTLER_RUNTIME_PUSH", "1")
        monkeypatch.setenv("BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS", "0")
        monkeypatch.setenv("WECHAT_TOKEN", "t")
        monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "user1")

        seen: dict[str, Any] = {}

        async def _fake_send(**kwargs):
            seen["chat_id"] = kwargs["chat_id"]
            return {}

        async def _driver() -> bool:
            # 在事件循环里同步调 push_runtime_message — 模拟 MCP tool
            # handler 同步路径里调 notify 的场景。
            return notify.push_runtime_message("t", "body")

        with patch(
            "butler.gateway.platforms.wechat_ilink.send_wechat_direct",
            side_effect=_fake_send,
        ):
            # 在已运行 loop 内调 _driver → 内部同步调 push_runtime_message
            loop = asyncio.new_event_loop()
            try:
                ok = loop.run_until_complete(_driver())
            finally:
                loop.close()

        assert ok is True, "push_runtime_message 在运行 loop 内应正常返回"
        assert seen["chat_id"] == "user1"

    def test_push_does_not_use_asyncio_run_directly(
        self, butler_home_push, monkeypatch,
    ):
        """push_runtime_message 不应再直接用 asyncio.run()。

        用静态检查: ``asyncio.run`` 在 butler/runtime/notify.py 中不应出现。
        """
        import inspect

        from butler.runtime import notify as notify_module

        source = inspect.getsource(notify_module)
        # 不应在 push_runtime_message 函数体内出现 asyncio.run 调用
        # (其他函数如有合法用途不在此限, 但本修复目的是改掉它)
        # 简单检查: notify 模块中应无 asyncio.run
        assert "asyncio.run(" not in source, (
            "butler/runtime/notify.py 仍含 asyncio.run( 调用, "
            "应改用 butler.mcp.async_runner.run_mcp_async 避免事件循环冲突"
        )


from typing import Any
