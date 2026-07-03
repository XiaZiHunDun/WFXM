"""Terminal approval best-effort helpers (P0-A)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def canonicalize_command_safe(command: str) -> str:
    def _run() -> str:
        from butler.tools.command_canonicalize import canonicalize_command_for_approval

        return str(canonicalize_command_for_approval(command) or "")

    result = safe_best_effort(
        _run,
        label="terminal_approval.canonicalize",
        default=(command or "").strip(),
    )
    return str(result or (command or "").strip())


def try_auto_review_terminal_safe(command: str) -> Any | None:
    def _run() -> Any:
        from butler.core.auto_review import try_auto_review_terminal

        return try_auto_review_terminal(command, diagnostics=None)

    return safe_best_effort(
        _run,
        label="terminal_approval.auto_review",
        default=None,
    )


def read_approval_record_safe(path: Path) -> dict[str, Any] | None:
    def _run() -> dict[str, Any]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("approval record is not a dict")
        return data

    result = safe_best_effort(
        _run,
        label="terminal_approval.read_record",
        default=None,
    )
    return result if isinstance(result, dict) else None
