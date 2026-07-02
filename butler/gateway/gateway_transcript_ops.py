"""Best-effort gateway transcript side effects (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def record_gateway_tool_action_safe(
    session_key: str,
    *,
    tool_name: str,
    args_preview: str = "",
) -> None:
    sk = str(session_key or "").strip()
    name = str(tool_name or "").strip()
    if not sk or not name:
        return

    def _run() -> None:
        from butler.core.session_transcript import record_tool_action

        record_tool_action(
            sk,
            tool_name=name[:64],
            args_preview=str(args_preview or "")[:400],
            source="gateway",
        )

    safe_best_effort(_run, label="gateway_transcript.tool_action", default=None)
