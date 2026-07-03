"""CC bridge best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def call_on_complete_safe(on_complete: Callable[[Any], None], finished: Any) -> None:
    def _run() -> None:
        on_complete(finished)

    safe_best_effort(_run, label="cc_bridge.on_complete", default=None)


def push_cc_bridge_completion_safe(job: Any) -> bool:
    def _run() -> bool:
        from butler.runtime.cc_bridge import format_cc_bridge_result
        from butler.runtime.notify import push_runtime_message

        title = "CC 桥接完成" if job.status == "completed" else "CC 桥接失败"
        return bool(push_runtime_message(f"[Butler] {title}", format_cc_bridge_result(job)))

    result = safe_best_effort(
        _run,
        label="cc_bridge.push_completion",
        default=False,
    )
    return bool(result)
