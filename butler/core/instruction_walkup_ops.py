"""Instruction walkup best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def session_key_safe(session_key: str = "") -> str:
    if session_key.strip():
        return session_key.strip()

    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "default")

    result = safe_best_effort(_run, label="instruction_walkup.session_key", default="default")
    return result if isinstance(result, str) and result else "default"


def resolve_rules_block_safe(resolved: Path, *, workspace_root: Path | None) -> str:
    def _run() -> str:
        from butler.core.rules_engine import resolve_rules_for_path

        return str(resolve_rules_for_path(resolved, workspace_root=workspace_root) or "")

    result = safe_best_effort(_run, label="instruction_walkup.rules", default="")
    return result if isinstance(result, str) else ""
