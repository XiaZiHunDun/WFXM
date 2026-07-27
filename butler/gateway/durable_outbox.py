"""Shim: durable_outbox moved to butler.resilience.durable_outbox.

This module exists only for mypy compatibility.
Use `from butler.resilience import durable_outbox` instead.
"""

from __future__ import annotations

from butler.resilience.durable_outbox import *  # noqa: F403

__all__ = [
    "durable_outbox_enabled",
    "durable_outbox_root",
    "durable_outbox_path_for_message",
    "durable_outbox_queue_message",
    "durable_outbox_pending_files",
    "durable_outbox_deliver_pending",
    "durable_outbox_deliver_single",
    "durable_outbox_mark_sent",
    "durable_outbox_cleanup",
]