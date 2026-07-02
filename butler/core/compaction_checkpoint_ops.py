"""Best-effort compaction checkpoint helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def restore_checkpoint_summary_acl(
    preview: Any,
    diagnostics: dict[str, Any],
) -> None:
    def _run() -> None:
        from butler.core.compaction_context_adapter import (
            apply_compaction_view_to_diagnostics,
            to_loop_compaction_view,
        )

        view = to_loop_compaction_view(preview, source="checkpoint_restore")
        diagnostics["compaction_checkpoint_summary_preview"] = view.content[:500]
        apply_compaction_view_to_diagnostics(view, diagnostics)

    safe_best_effort(_run, label="compaction_checkpoint.acl_restore", default=None)


def loop_model_name(loop: Any) -> str:
    def _run() -> str:
        client = getattr(loop, "client", None)
        return str(getattr(client, "model", "") or "")

    result = safe_best_effort(_run, label="compaction_checkpoint.loop_model", default="")
    return result if isinstance(result, str) else ""


def open_todos_count(session_key: str) -> int:
    def _run() -> int:
        from butler.core.session_todos import count_open_todos, session_todos_enabled

        if not session_todos_enabled():
            return 0
        return int(count_open_todos(session_key))

    result = safe_best_effort(_run, label="compaction_checkpoint.open_todos", default=0)
    return int(result) if isinstance(result, int) else 0
