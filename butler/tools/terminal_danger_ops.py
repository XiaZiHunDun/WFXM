"""Terminal danger check best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def evaluate_execpolicy_safe(command: str) -> Any | None:
    def _run() -> Any:
        from butler.execpolicy import evaluate_command
        from butler.execution_context import get_current_orchestrator

        workspace: Path | None = None
        orch = get_current_orchestrator()
        if orch is not None and getattr(orch, "project_manager", None):
            proj = orch.project_manager.get_current()
            if proj is not None:
                workspace = Path(getattr(proj, "workspace", "") or "")
        return evaluate_command(command, workspace=workspace)

    return safe_best_effort(
        _run,
        label="terminal_danger.execpolicy",
        default=None,
    )


def is_terminal_pattern_approved_safe(session_key: str, pattern_name: str) -> bool:
    def _run() -> bool:
        from butler.tools.terminal_pattern_approval import is_pattern_approved

        return bool(is_pattern_approved(session_key, pattern_name))

    result = safe_best_effort(
        _run,
        label="terminal_danger.pattern_approval",
        default=False,
    )
    if result is None:
        logger.debug("terminal pattern approval lookup skipped")
    return bool(result)
