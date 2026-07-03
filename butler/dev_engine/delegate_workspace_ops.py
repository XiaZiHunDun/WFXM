"""Delegate workspace seeding best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def seed_isolated_workspace_read_state_safe(ws: Path, *, session_key: str) -> None:
    def _run() -> None:
        from butler.dev_engine.b9_delegate_gate import seed_b9_workspace_read_state

        seed_b9_workspace_read_state(ws, session_key=session_key, max_depth=2)

    safe_best_effort(_run, label="delegate_workspace.read_state_seed", default=None)
