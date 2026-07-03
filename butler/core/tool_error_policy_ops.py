"""Tool error policy telemetry best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def inc_tool_error_policy_metric_safe(*, kind: str, tool_name: str) -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import inc

        inc(
            "tool_error_policy",
            labels={"kind": kind, "tool": (tool_name or "?")[:32]},
        )

    safe_best_effort(_run, label="tool_error_policy.metric", default=None)
