"""Best-effort helpers for owner PMF metrics (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def owner_edit_slash_expanded_safe(text: str) -> bool:
    def _run() -> bool:
        from butler.gateway.owner_delegate_shortcuts import try_expand_owner_edit_slash

        return bool(try_expand_owner_edit_slash(text))

    return safe_best_effort(_run, label="owner_pmf.edit_slash", default=False) is True
