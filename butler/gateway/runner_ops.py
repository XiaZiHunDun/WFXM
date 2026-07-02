"""Gateway runner best-effort helpers (P0-A)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from butler.core.best_effort import async_safe_best_effort, safe_best_effort

logger = logging.getLogger(__name__)


def warmup_gateway_runtime_safe(butler: Any) -> None:
    def _skills() -> None:
        from butler.skills.similarity import _ensure_jieba

        _ensure_jieba()
        mgr = getattr(butler._orchestrator, "_skill_manager", None)
        if mgr is not None:
            mgr.list_skills()
        logger.info("Gateway runtime warmup complete (skills/jieba)")

    safe_best_effort(_skills, label="runner.warmup_skills", default=None)

    def _degradation() -> None:
        from butler.ops.degradation_registry import sync_all_startup_degradations

        sync_all_startup_degradations()

    safe_best_effort(_degradation, label="runner.warmup_degradation", default=None)


def restore_persisted_queue_safe() -> int:
    def _run() -> int:
        from butler.gateway.message_queue import restore_persisted_queue

        return int(restore_persisted_queue() or 0)

    result = safe_best_effort(_run, label="runner.queue_restore", default=0)
    return int(result or 0)


async def disconnect_adapter_safe(adapter: Any) -> None:
    async def _run() -> None:
        await adapter.disconnect()

    await async_safe_best_effort(
        _run,
        label=f"runner.disconnect.{getattr(adapter, 'name', '?')}",
        default=None,
    )


def shutdown_mcp_stack_safe() -> None:
    def _run() -> None:
        from butler.mcp.async_runner import graceful_shutdown_mcp_stack

        graceful_shutdown_mcp_stack(timeout=5.0)

    safe_best_effort(_run, label="runner.mcp_shutdown", default=None)


def close_semantic_indices_safe() -> None:
    def _run() -> None:
        from butler.memory.semantic_index import close_all_semantic_indices

        close_all_semantic_indices()

    safe_best_effort(_run, label="runner.semantic_index_shutdown", default=None)


def sync_send_via_adapter_loud(
    adapters: list[Any],
    chat_id: str,
    text: str,
) -> bool:
    """Send via first adapter; log warning and try next on failure."""
    if not chat_id or not text:
        return False
    for adapter in adapters:
        if not hasattr(adapter, "send"):
            continue
        try:
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    adapter.send(chat_id, text), loop
                ).result(timeout=30)
            else:
                asyncio.run(adapter.send(chat_id, text))
            return True
        except Exception as exc:
            logger.warning("_sync_send_via_adapter failed: %s", exc)
            continue
    logger.warning("No adapter with send() available")
    return False


def push_reminder_safe(adapters: list[Any], reminder: dict[str, Any]) -> None:
    def _run() -> None:
        import os

        from butler.gateway.durable_outbox import (
            durable_outbox_enabled,
            enqueue_outbox_message,
            mark_outbox_sent,
        )

        text = f"⏰ 提醒：{reminder.get('message', '')}\n（设定时间：{reminder.get('due_human', '')}）"
        chat_id = os.getenv("BUTLER_OWNER_WECHAT_ID", "")
        if not chat_id:
            logger.warning(
                "BUTLER_OWNER_WECHAT_ID not set, reminder not pushed: %s",
                reminder.get("id"),
            )
            return
        if durable_outbox_enabled():
            entry_id = enqueue_outbox_message(chat_id, text, kind="reminder")
            if sync_send_via_adapter_loud(adapters, chat_id, text):
                mark_outbox_sent(entry_id)
                logger.info("Reminder sent+marked via outbox: %s", reminder.get("id"))
            else:
                logger.warning(
                    "Reminder enqueued but send failed (will retry on replay): %s",
                    reminder.get("id"),
                )
        elif sync_send_via_adapter_loud(adapters, chat_id, text):
            logger.info("Reminder fired (direct): %s", reminder.get("id"))
        else:
            logger.warning("Reminder direct send failed: %s", reminder.get("id"))

    safe_best_effort(_run, label="runner.reminder_push", default=None)


def poll_due_reminders_safe() -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        from butler.tools.reminder import poll_due_reminders

        fired = poll_due_reminders()
        return fired if isinstance(fired, list) else []

    result = safe_best_effort(_run, label="runner.reminder_poll", default=[])
    return result if isinstance(result, list) else []


def replay_outbox_entry_safe(
    adapters: list[Any],
    entry: dict[str, Any],
) -> bool:
    """Replay one outbox entry; return True if sent and marked."""
    from butler.gateway.durable_outbox import mark_outbox_sent

    chat_id = entry.get("chat_id", "")
    body = entry.get("body", "")
    entry_id = entry.get("entry_id", "")
    if not chat_id or not body:
        return False
    if not sync_send_via_adapter_loud(adapters, chat_id, body):
        logger.warning("Outbox replay send failed for entry %s", entry_id)
        return False
    mark_outbox_sent(entry_id)
    return True


def replay_pending_outbox_safe(adapters: list[Any]) -> tuple[int, int]:
    """Return (sent_count, total_pending)."""
    def _run() -> tuple[int, int]:
        from butler.gateway.durable_outbox import (
            durable_outbox_enabled,
            list_pending_outbox,
        )

        if not durable_outbox_enabled():
            return 0, 0
        pending = list_pending_outbox()
        if not pending:
            return 0, 0
        sent = 0
        for entry in pending:
            if replay_outbox_entry_safe(adapters, entry):
                sent += 1
        return sent, len(pending)

    result = safe_best_effort(_run, label="runner.outbox_replay", default=(0, 0))
    if isinstance(result, tuple) and len(result) == 2:
        return int(result[0]), int(result[1])
    return 0, 0
