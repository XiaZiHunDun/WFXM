"""Post-commit callback best-effort helpers (P0-A)."""

from __future__ import annotations

from collections.abc import Callable

from butler.core.best_effort import safe_best_effort


def run_after_commit_callback_safe(fn: Callable[[], None]) -> bool:
    def _run() -> bool:
        fn()
        return True

    result = safe_best_effort(_run, label="post_commit.callback", default=False)
    return bool(result)
