"""Best-effort helpers for tool dispatch (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def annotate_mutation_not_landed_safe(
    tool_name: str,
    result: str,
) -> tuple[str, bool]:
    def _run() -> tuple[str, bool]:
        from butler.core.tool_result_classification import annotate_mutation_not_landed

        out = annotate_mutation_not_landed(tool_name, result)
        if isinstance(out, tuple) and len(out) == 2:
            return str(out[0]), bool(out[1])
        return result, False

    annotated = safe_best_effort(
        _run,
        label="tool_dispatch.mutation_landed",
        default=None,
    )
    if isinstance(annotated, tuple) and len(annotated) == 2:
        out, failed = annotated
        return str(out), bool(failed)
    return result, False
