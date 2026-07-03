"""Context budget usage ledger best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def record_usage_snapshot_safe(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int,
    provider: str,
    model: str,
) -> None:
    def _run() -> None:
        from butler.ops.usage_ledger import record_usage_snapshot

        record_usage_snapshot(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            provider=provider,
            model=model,
        )

    safe_best_effort(_run, label="context_budget.usage_snapshot", default=None)
