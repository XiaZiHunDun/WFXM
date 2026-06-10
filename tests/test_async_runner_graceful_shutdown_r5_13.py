"""R5-13: MCP stack drains connections before async loop shutdown."""

from __future__ import annotations

import signal
import threading
from unittest.mock import MagicMock, patch

import pytest

from butler.mcp import async_runner


@pytest.fixture(autouse=True)
def _reset_async_runner_shutdown_state():
    saved = (
        async_runner._loop,
        async_runner._thread,
        async_runner._shutdown_done,
        async_runner._signal_registered,
        dict(async_runner._prev_signal_handlers),
    )
    async_runner._loop = None
    async_runner._thread = None
    async_runner._shutdown_done = False
    async_runner._signal_registered = False
    async_runner._prev_signal_handlers.clear()
    yield
    try:
        async_runner.shutdown_async_runner(timeout=2.0)
    except Exception:
        pass
    (
        async_runner._loop,
        async_runner._thread,
        async_runner._shutdown_done,
        async_runner._signal_registered,
        async_runner._prev_signal_handlers,
    ) = saved


@pytest.mark.unit
def test_graceful_shutdown_disconnects_mcp_before_loop_stop(monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_ENABLED", "1")
    calls: list[str] = []

    class _Mgr:
        def disconnect_all(self) -> None:
            calls.append("disconnect")

    with patch("butler.mcp.config.mcp_enabled", return_value=True), patch(
        "butler.mcp.manager.get_manager",
        return_value=_Mgr(),
    ), patch.object(async_runner, "shutdown_async_runner", return_value=True) as mock_shutdown:
        ok = async_runner.graceful_shutdown_mcp_stack(timeout=5.0)

    assert ok is True
    assert calls == ["disconnect"]
    mock_shutdown.assert_called_once_with(timeout=5.0)


@pytest.mark.unit
def test_signal_handler_registered_on_first_ensure_loop():
    with patch("signal.signal") as mock_signal, patch(
        "signal.getsignal",
        return_value=signal.SIG_DFL,
    ):
        async_runner._register_signal_shutdown()
        assert mock_signal.called
        registered = {call.args[0] for call in mock_signal.call_args_list}
        assert signal.SIGTERM in registered or signal.SIGINT in registered


@pytest.mark.unit
def test_signal_handler_drains_mcp_stack():
    handler = None

    def _capture(sig, fn):
        nonlocal handler
        handler = fn

    with patch("signal.signal", side_effect=_capture), patch(
        "signal.getsignal",
        return_value=signal.SIG_DFL,
    ), patch.object(
        async_runner,
        "graceful_shutdown_mcp_stack",
        return_value=True,
    ) as mock_graceful:
        async_runner._register_signal_shutdown()
        assert handler is not None
        handler(signal.SIGTERM, None)
        mock_graceful.assert_called_once_with(timeout=5.0)


@pytest.mark.unit
def test_atexit_disconnects_before_loop_shutdown(monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_ENABLED", "1")
    calls: list[str] = []

    class _Mgr:
        def disconnect_all(self) -> None:
            calls.append("disconnect")

    with patch("butler.mcp.config.mcp_enabled", return_value=True), patch(
        "butler.mcp.manager.get_manager",
        return_value=_Mgr(),
    ), patch.object(async_runner, "shutdown_async_runner", return_value=True) as mock_shutdown:
        async_runner._atexit_shutdown()

    assert calls == ["disconnect"]
    mock_shutdown.assert_called_once_with(timeout=2.0)
