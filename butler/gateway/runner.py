"""Butler-native gateway runner (no Hermes subprocess)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import signal
from typing import Any

from butler.gateway.message_handler import ButlerMessageHandler
from butler.gateway.platform_policy import SUPPORTED_PLATFORMS, normalize_platforms

NATIVE_PLATFORMS = SUPPORTED_PLATFORMS  # alias for tests / legacy imports
from butler.gateway.platforms.types import MessageEvent, PlatformConfig  # noqa: E402

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
_HANDLER_TIMEOUT_SECONDS = float(os.getenv("BUTLER_GATEWAY_HANDLER_TIMEOUT", "600"))


def unsupported_platforms(platforms: list[str]) -> list[str]:
    from butler.gateway.platform_policy import unsupported_platforms as _unsupported

    return _unsupported(platforms)


def _warmup_gateway_runtime(butler: ButlerMessageHandler) -> None:
    """Avoid first user message blocking on jieba/skill index cold start."""
    try:
        from butler.skills.similarity import _ensure_jieba

        _ensure_jieba()
        mgr = getattr(butler._orchestrator, "_skill_manager", None)
        if mgr is not None:
            mgr.list_skills()
        logger.info("Gateway runtime warmup complete (skills/jieba)")
    except Exception as exc:
        logger.debug("Gateway warmup skipped: %s", exc)


async def _butler_message_handler(
    butler: ButlerMessageHandler,
    event: MessageEvent,
    *,
    platform: str = "wechat",
) -> str | None:
    from butler.gateway.inbound_media import build_inbound_user_text

    text = build_inbound_user_text(event).strip()
    if not text:
        return None
    source = event.source
    if source is None:
        return None
    bridge = getattr(event, "gateway_bridge", None)
    handler_timeout = _HANDLER_TIMEOUT_SECONDS

    def _run_in_worker() -> str:
        from butler.gateway.outbound_bridge import set_current_bridge

        if bridge is not None:
            set_current_bridge(bridge)
        try:
            return butler.handle_message(
                text,
                platform=platform,
                external_id=source.chat_id,
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
    unsupported = unsupported_platforms(platforms)
    if unsupported:
        from butler.gateway.platform_policy import format_unsupported_error

        logger.error("%s", format_unsupported_error(unsupported))
        return 2

    butler = ButlerMessageHandler(channel="gateway")
    _warmup_gateway_runtime(butler)
    adapters: list[Any] = []

    for name in platforms:
        if name in ("wechat", "weixin"):
            from butler.gateway.platforms.wechat import WeChatAdapter, check_wechat_requirements

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

    try:
        from butler.gateway.message_queue import restore_persisted_queue

        restored = restore_persisted_queue()
        if restored:
            logger.info("Restored %d queued inbound messages from disk", restored)
    except Exception as exc:
        logger.debug("Queue restore skipped: %s", exc)

    _replay_pending_outbox(connected)

    _reminder_task = asyncio.ensure_future(_poll_reminders_loop(connected))

    stop = asyncio.Event()

    def _request_stop(*_args: Any) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop.set())

    await stop.wait()

    _reminder_task.cancel()
    for adapter in connected:
        await adapter.disconnect()
    return 0


async def _poll_reminders_loop(adapters: list[Any]) -> None:
    """Background coroutine that checks for due reminders every 60s."""
    poll_interval = float(os.getenv("BUTLER_REMINDER_POLL_SECONDS", "60"))
    while True:
        await asyncio.sleep(poll_interval)
        try:
            from butler.tools.reminder import poll_due_reminders

            fired = poll_due_reminders()
            if not fired:
                continue
            bridge = None
            for adapter in adapters:
                if hasattr(adapter, "send_text"):
                    bridge = adapter
                    break
            if bridge is None:
                continue
            for reminder in fired:
                text = f"⏰ 提醒：{reminder.get('message', '')}\n（设定时间：{reminder.get('due_human', '')}）"
                try:
                    chat_id = os.getenv("BUTLER_OWNER_WECHAT_ID", "")
                    if chat_id:
                        bridge.send_text(chat_id, text)
                        logger.info("Reminder fired: %s", reminder.get("id"))
                    else:
                        logger.warning("BUTLER_OWNER_WECHAT_ID not set, reminder not pushed: %s", reminder.get("id"))
                except Exception as exc:
                    logger.warning("Reminder push failed: %s", exc)
        except Exception as exc:
            logger.debug("Reminder poll error: %s", exc)


def _replay_pending_outbox(adapters: list[Any]) -> None:
    """Replay unsent durable outbox entries on gateway startup."""
    try:
        from butler.gateway.durable_outbox import (
            durable_outbox_enabled,
            list_pending_outbox,
            mark_outbox_sent,
        )

        if not durable_outbox_enabled():
            return

        pending = list_pending_outbox()
        if not pending:
            return

        logger.info("Replaying %d pending outbox entries", len(pending))
        bridge = None
        for adapter in adapters:
            if hasattr(adapter, "send_text"):
                bridge = adapter
                break

        if bridge is None:
            logger.warning("No adapter with send_text — skipping outbox replay")
            return

        sent = 0
        for entry in pending:
            chat_id = entry.get("chat_id", "")
            text = entry.get("text", "")
            entry_id = entry.get("id", "")
            if not chat_id or not text:
                continue
            try:
                bridge.send_text(chat_id, text)
                mark_outbox_sent(entry_id)
                sent += 1
            except Exception as exc:
                logger.warning("Outbox replay failed for entry %s: %s", entry_id, exc)
        logger.info("Outbox replay complete: %d/%d sent", sent, len(pending))
    except ImportError:
        logger.debug("durable_outbox not available, skipping replay")
    except Exception as exc:
        logger.warning("Outbox replay error: %s", exc)


def run_gateway_blocking(platforms: list[str]) -> int:
    from butler.logging_config import configure_logging

    configure_logging()
    try:
        return asyncio.run(run_gateway_async(platforms))
    except KeyboardInterrupt:
        return 0
