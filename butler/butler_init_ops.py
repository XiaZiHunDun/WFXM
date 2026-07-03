"""Butler package init best-effort helpers (P0-A)."""

from __future__ import annotations

import subprocess

from butler.core.best_effort import safe_best_effort


def resolve_git_sha_safe() -> str:
    def _run() -> str:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
            .decode()
            .strip()
        )

    result = safe_best_effort(_run, label="butler_init.git_sha", default="unknown")
    text = str(result or "").strip()
    return text or "unknown"
