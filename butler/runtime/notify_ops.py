"""Runtime notify best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def push_runtime_wechat_safe(
    send_fn: Callable[[], dict[str, Any]],
    *,
    title: str,
    body: str,
    chat_id: str,
    mark_sent: Callable[[], None],
    is_rate_limit_error: Callable[[str | None], bool],
    should_enqueue_failure: Callable[[str | None], bool],
    enqueue_failure: Callable[[str, str, str], None],
    record_rate_limit_failure: Callable[[], None],
) -> bool:
    try:
        result = send_fn()
        ok = not result.get("error")
        if ok:
            mark_sent()
        else:
            err = result.get("error")
            logger.warning("Runtime wechat push failed: %s", err)
            if is_rate_limit_error(str(err)):
                record_rate_limit_failure()
            if should_enqueue_failure(err):
                enqueue_failure(title, body, chat_id)
        return ok
    except Exception as exc:
        logger.exception("Runtime wechat push failed: %s", exc)
        if is_rate_limit_error(str(exc)):
            record_rate_limit_failure()
        if should_enqueue_failure(str(exc)):
            enqueue_failure(title, body, chat_id)
        return False
