"""Outbound bridge harness for WeChat scenario sim (H4–H6 push equivalence)."""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from butler.gateway.outbound_bridge import GatewayOutboundBridge, set_current_bridge
from butler.gateway.outbound_bridge_ops import schedule_coro_threadsafe

_MISSING = object()


def wait_background_delegates(*, timeout: float = 420.0) -> None:
    from butler.runtime.async_delegate import _LOCK, _THREADS

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with _LOCK:
            alive = any(t.is_alive() for t in _THREADS.values())
        if not alive:
            return
        time.sleep(0.25)


@dataclass
class OutboundCapture:
    bodies: list[str] = field(default_factory=list)


class _RecordingAdapter:
    def __init__(self, capture: OutboundCapture) -> None:
        self._capture = capture

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        body = (content or "").strip()
        if body:
            self._capture.bodies.append(body)
        from butler.gateway.platforms.types import SendResult

        return SendResult(success=True)

    async def send_typing(self, chat_id: str, metadata: dict[str, Any] | None = None) -> None:
        return None

    async def stop_typing(self, chat_id: str) -> None:
        return None


@dataclass
class SimOutboundHarness:
    chat_id: str
    ack_seconds: float = 3.0
    capture: OutboundCapture = field(default_factory=OutboundCapture)
    _loop: asyncio.AbstractEventLoop = field(init=False)
    _thread: threading.Thread = field(init=False)
    _bridge: GatewayOutboundBridge = field(init=False)
    _ready: threading.Event = field(default_factory=threading.Event)
    _patch_token: Any = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        adapter = _RecordingAdapter(self.capture)
        self._bridge = GatewayOutboundBridge(adapter=adapter, chat_id=self.chat_id, loop=self._loop)
        self._bridge.ack_seconds = self.ack_seconds
        self._bridge.ack_enabled = True

    def _loop_main(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop_main, name="sim-outbound-loop", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("sim outbound loop failed to start")
        fut = asyncio.run_coroutine_threadsafe(self._bridge.start_turn(), self._loop)
        fut.result(timeout=10)

    def stop(self) -> None:
        try:
            fut = asyncio.run_coroutine_threadsafe(self._bridge.end_turn(), self._loop)
            fut.result(timeout=10)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)

    def _patched_schedule(
        self,
        _loop: asyncio.AbstractEventLoop,
        coro_factory: Callable[[], Any],
        *,
        label: str,
    ) -> bool:
        coro = coro_factory()
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        fut.result(timeout=120)
        return True

    @contextmanager
    def worker_bridge(self) -> Iterator[GatewayOutboundBridge]:
        import butler.gateway.outbound_bridge_ops as ops
        from butler.gateway.gateway_contracts import register_gateway_contracts

        register_gateway_contracts()
        self._patch_token = ops.schedule_coro_threadsafe
        ops.schedule_coro_threadsafe = self._patched_schedule  # type: ignore[assignment]
        set_current_bridge(self._bridge)
        orch_token: Any = None
        try:
            from butler.execution_context import get_current_orchestrator

            orch = get_current_orchestrator()
            if orch is not None:
                orch_token = (orch, getattr(orch, "__dict__", {}).get("gateway_bridge", _MISSING))
                orch.__dict__["gateway_bridge"] = self._bridge
            yield self._bridge
        finally:
            if orch_token is not None:
                orch, prev = orch_token
                if prev is _MISSING:
                    orch.__dict__.pop("gateway_bridge", None)
                else:
                    orch.__dict__["gateway_bridge"] = prev
            set_current_bridge(None)
            if self._patch_token is not None:
                ops.schedule_coro_threadsafe = self._patch_token  # type: ignore[assignment]
                self._patch_token = None

    def drain(self, *, seconds: float = 2.0) -> None:
        fut = asyncio.run_coroutine_threadsafe(asyncio.sleep(seconds), self._loop)
        fut.result(timeout=seconds + 5)


def run_handler_with_outbound_sim(
    handler_call: Callable[[], str],
    *,
    chat_id: str,
    ack_seconds: float = 3.0,
    drain_seconds: float = 2.0,
    wait_delegate_seconds: float = 420.0,
) -> tuple[str, OutboundCapture]:
    harness = SimOutboundHarness(chat_id=chat_id, ack_seconds=ack_seconds)
    harness.start()
    try:
        with harness.worker_bridge() as bridge:
            reply = handler_call()
            bridge.mark_final_sent(main_reply_chars=len(reply or ""))
            wait_background_delegates(timeout=wait_delegate_seconds)
            harness.drain(seconds=drain_seconds)
            bridge.maybe_notify_turn_complete_after_reply()
        return reply, harness.capture
    finally:
        harness.stop()


__all__ = ["OutboundCapture", "SimOutboundHarness", "run_handler_with_outbound_sim"]
