"""B9 harness audit best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any, cast

from butler.core.best_effort import safe_best_effort


def mine_delegate_failure_signatures_safe(
    *,
    limit: int = 300,
    min_count: int = 1,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        from butler.ops.b9_failure_analysis import mine_delegate_failure_signatures

        return cast(dict[str, Any], mine_delegate_failure_signatures(limit=limit, min_count=min_count))

    result = safe_best_effort(
        _run,
        label="b9_harness_audit.mine_signatures",
        default={},
    )
    return result if isinstance(result, dict) else {}
