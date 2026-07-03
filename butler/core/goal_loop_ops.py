"""Goal loop token accounting best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def record_goal_tokens_safe(session_key: str, tokens: int) -> None:
    def _run() -> None:
        from butler.core.goal_loop import record_goal_tokens

        record_goal_tokens(session_key, int(tokens))

    safe_best_effort(_run, label="goal_loop.record_tokens", default=None)
