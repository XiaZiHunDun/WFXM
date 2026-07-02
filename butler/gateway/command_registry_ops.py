"""Slash command dispatch error envelope (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def dispatch_registered_command(
    *,
    cmd: str,
    handler: Callable[[Any], str | None],
    ctx: Any,
    on_success: Callable[[], None] | None = None,
) -> tuple[bool, str | None]:
    try:
        result = handler(ctx)
        if result is not None and on_success is not None:
            on_success()
        return True, result
    except Exception as exc:
        logger.error("Command handler %s failed: %s", cmd, exc, exc_info=True)
        return True, f"命令执行异常: {exc}"
