"""Butler-native gateway runner (no Hermes subprocess)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import signal
import threading
import time
from typing import Any, cast

from butler import format_build_identity_line, mark_start_time
from butler.gateway.message_handler import ButlerMessageHandler
from butler.gateway.platform_policy import (
    SUPPORTED_PLATFORMS,
    format_unsupported_error,
    normalize_platforms,
    unsupported_platforms as _unsupported_platforms,
)
from butler.gateway.inbound_media import build_inbound_user_text
from butler.gateway.outbound_bridge import set_current_bridge
from butler.gateway.platforms.wechat import WeChatAdapter, check_wechat_requirements
from butler.gateway.runner_ops import (
    close_semantic_indices_safe,
    disconnect_adapter_safe,
    poll_due_reminders_safe,
    push_reminder_safe,
    replay_pending_outbox_safe,
    restore_persisted_queue_safe,
    shutdown_mcp_stack_safe,
    sync_send_via_adapter_loud,
    warmup_gateway_runtime_safe,
)
from butler.gateway.singleton_lock import acquire_gateway_singleton_lock
from butler.gateway.events_sink import register_gateway_events_sink
from butler.gateway.gateway_contracts import register_gateway_contracts
from butler.logging_config import configure_logging

NATIVE_PLATFORMS = SUPPORTED_PLATFORMS  # alias for tests / legacy imports
from butler.gateway.platforms.types import MessageEvent, PlatformConfig  # noqa: E402
# R1-3: install the gateway implementation of butler.core.events_sink on
# import. Core (context_compressor / compaction_task / compaction_steer_bridge)
# calls the shims in core.events_sink; this is what makes them run for real
# when the gateway is up.
from butler.gateway import events_sink_impl  # noqa: E402, F401
from butler.ops.runtime_metrics_sink import install_runtime_metrics_sink  # noqa: E402

install_runtime_metrics_sink()
from butler.env_parse import float_env, init_dotenv  # noqa: E402

init_dotenv()

logger = logging.getLogger(__name__)

# Re-export for tests / callers that imported from runner.
__all__ = [
    "NATIVE_PLATFORMS",
    "normalize_platforms",
    "unsupported_platforms",
    "run_gateway_blocking",
    "run_gateway_async",
]

def _handler_worker_count() -> int:
    raw = os.getenv("BUTLER_GATEWAY_HANDLER_WORKERS", "2")
    try:
        return max(1, min(8, int(raw)))
    except ValueError:
        return 2


# Per-chat session locks serialize same user; >1 worker allows /详细 during long turns.
_HANDLER_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=_handler_worker_count(),
    thread_name_prefix="butler-gw-handler",
)
_HANDLER_TIMEOUT_SECONDS = float_env("BUTLER_GATEWAY_HANDLER_TIMEOUT", 600.0, min=1.0)
_HANDLER_SHUTDOWN_GRACE_SECONDS = float_env(
    "BUTLER_GATEWAY_HANDLER_SHUTDOWN_GRACE",
    30.0,
    min=0.0,
)

# Sprint 16 REL-11-4: 让 in-flight handler (executor 线程) 能感知 shutdown
# 阶段。 asyncio.Event 在子线程中无法 set / wait, 必须用 threading.Event。
_SHUTDOWN_EVENT = threading.Event()


def is_shutting_down() -> bool:
    """Return True once the gateway has entered its shutdown phase.

    Handlers running inside ``_HANDLER_EXECUTOR`` should check this before
    doing expensive work; submit paths should also gate new submissions.
    """
    return _SHUTDOWN_EVENT.is_set()


def request_stop(stop: asyncio.Event) -> None:
    """Idempotently set both the asyncio stop event and the threading shutdown event.

    Module-level so tests and external callers can trigger the same path that
    SIGINT / SIGTERM take. Safe to call multiple times.
    """
    _SHUTDOWN_EVENT.set()
    stop.set()


def unsupported_platforms(platforms: list[str]) -> list[str]:
    return cast(list[str], _unsupported_platforms(platforms))


def _warmup_gateway_runtime(butler: ButlerMessageHandler) -> None:
    warmup_gateway_runtime_safe(butler)


async def _butler_message_handler(
    butler: ButlerMessageHandler,
    event: MessageEvent,
    *,
    platform: str = "wechat",
) -> str | None:
    text = build_inbound_user_text(event).strip()
    if not text:
        return None
    source = event.source
    if source is None:
        return None
    if is_shutting_down():
        # REL-11-4: shutdown 阶段不再接受新提交, 避免挂在 executor 队列里被强杀
        logger.info(
            "Dropping inbound during shutdown (chat_id=%s preview=%r)",
            source.chat_id,
            text[:80],
        )
        return None
    bridge = getattr(event, "gateway_bridge", None)
    handler_timeout = _HANDLER_TIMEOUT_SECONDS
    # Session/owner/welcome keys must use stable chat_id, not per-message message_id.
    # Per-message dedup is handled in wechat_ilink (_phase_inbound_dedup) and optionally
    # via inbound_idempotency when a distinct inbound id is supplied.
    external_id = ""
    if source is not None:
        external_id = str(source.chat_id or "").strip()

    def _run_in_worker() -> str:
        if bridge is not None:
            set_current_bridge(bridge)
        try:
            return cast(
                str,
                butler.handle_message(
                    text,
                    platform=platform,
                    external_id=external_id or None,
                ),
            )
        finally:
            if bridge is not None:
                set_current_bridge(None)

    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_HANDLER_EXECUTOR, _run_in_worker),
            timeout=handler_timeout,
        )
    except asyncio.TimeoutError:
        logger.error(
            "Gateway handler timed out after %.0fs (chat_id=%s preview=%r)",
            handler_timeout,
            source.chat_id,
            text[:80],
        )
        if bridge is not None:
            bridge.notify_turn_timeout(timeout_seconds=handler_timeout)
        return (
            f"处理超时（>{int(handler_timeout)}秒）。"
            "请稍后重试，或发 /诊断 查看状态；必要时重启 butler-gateway。"
        )


async def run_gateway_async(platforms: list[str]) -> int:
    """Start native adapters; blocks until cancelled."""
    acquire_gateway_singleton_lock()

    register_gateway_events_sink()
    register_gateway_contracts()
    mark_start_time()
    logger.info("%s starting", format_build_identity_line())

    unsupported = unsupported_platforms(platforms)
    if unsupported:
        logger.error("%s", format_unsupported_error(unsupported))
        return 2

    butler = ButlerMessageHandler(channel="gateway")
    _warmup_gateway_runtime(butler)
    adapters: list[Any] = []

    for name in platforms:
        if name in ("wechat", "weixin"):
            if not check_wechat_requirements():
                logger.error("WeChat requires: pip install aiohttp cryptography certifi")
                return 1
            config = PlatformConfig(
                token=os.getenv("WECHAT_TOKEN", "") or os.getenv("WEIXIN_TOKEN", ""),
                extra={
                    "account_id": os.getenv("WECHAT_ACCOUNT_ID", "") or os.getenv("WEIXIN_ACCOUNT_ID", ""),
                },
            )
            adapter = WeChatAdapter(config)

            async def _handler(event: MessageEvent, _b: ButlerMessageHandler = butler) -> str | None:
                plat = (event.source.platform if event.source else None) or "wechat"
                return await _butler_message_handler(_b, event, platform=plat)

            adapter.set_message_handler(_handler)
            adapters.append(adapter)

    if not adapters:
        logger.error("No adapters to start")
        return 1

    connected = []
    for adapter in adapters:
        if await adapter.connect():
            connected.append(adapter)
        else:
            logger.error("[%s] connect failed: %s", adapter.name, getattr(adapter, "_fatal_error_message", ""))

    if not connected:
        return 1

    logger.info("Butler native gateway running (%s)", ", ".join(a.name for a in connected))

    restored = restore_persisted_queue_safe()
    if restored:
        logger.info("Restored %d queued inbound messages from disk", restored)

    _replay_pending_outbox(connected)

    _reminder_task = asyncio.ensure_future(_poll_reminders_loop(connected))

    stop = asyncio.Event()

    def _on_signal(*_args: Any) -> None:
        request_stop(stop)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            # R4-11: signal.signal fallback must not call asyncio.Event.set()
            # directly (not signal-safe). Set threading event only, then
            # schedule asyncio stop on the loop thread.
            def _on_signal_fallback(*_args: Any) -> None:
                _SHUTDOWN_EVENT.set()
                try:
                    loop.call_soon_threadsafe(stop.set)
                except RuntimeError:
                    pass

            signal.signal(sig, _on_signal_fallback)

    await stop.wait()

    # REL-11-4: 显式 set (signal handler 可能因 NotImplementedError 走 signal.signal 路径,
    # 仍要确保 _SHUTDOWN_EVENT 被 set, 兜底)
    _SHUTDOWN_EVENT.set()

    _reminder_task.cancel()
    for adapter in connected:
        await disconnect_adapter_safe(adapter)

    # Grace period: 给 in-flight handler 时间完成。 超时后强制退出, 避免进程挂住。
    grace = _HANDLER_SHUTDOWN_GRACE_SECONDS
    logger.info("Waiting up to %.0fs for in-flight handlers to drain", grace)
    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                _HANDLER_EXECUTOR.shutdown, wait=True, cancel_futures=False,
            ),
            timeout=grace,
        )
        logger.info("Handler executor drained cleanly")
    except asyncio.TimeoutError:
        logger.warning(
            "Handler executor still has in-flight tasks after %.0fs grace; "
            "exiting anyway (LLM calls may be aborted by OS)",
            grace,
        )

    shutdown_mcp_stack_safe()
    close_semantic_indices_safe()

    return 0


def _sync_send_via_adapter(adapters: list[Any], chat_id: str, text: str) -> bool:
    return bool(sync_send_via_adapter_loud(adapters, chat_id, text))


async def _poll_reminders_loop(adapters: list[Any]) -> None:
    """Background coroutine that checks for due reminders every 60s."""
    poll_interval = float_env("BUTLER_REMINDER_POLL_SECONDS", 60)
    while True:
        await asyncio.sleep(poll_interval)
        fired = poll_due_reminders_safe()
        if not fired:
            continue
        for reminder in fired:
            push_reminder_safe(adapters, reminder)


def _replay_pending_outbox(adapters: list[Any]) -> None:
    """Replay unsent durable outbox entries on gateway startup."""
    sent, total = replay_pending_outbox_safe(adapters)
    if total:
        logger.info("Replaying %d pending outbox entries", total)
        logger.info("Outbox replay complete: %d/%d sent", sent, total)


def run_gateway_blocking(platforms: list[str]) -> int:
    configure_logging()
    try:
        return asyncio.run(run_gateway_async(platforms))
    except KeyboardInterrupt:
        return 0
