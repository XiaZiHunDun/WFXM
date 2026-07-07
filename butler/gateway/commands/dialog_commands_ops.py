"""Dialog command best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.gateway.owner_surface import format_project_switch_brief
from butler.core.session_transcript import record_session_reset
from butler.hooks.telemetry import reset_hook_telemetry
from butler.gateway.completion_telemetry import reset_completion_telemetry
from butler.core.read_state import reset_read_state
from butler.gateway.message_queue import reset_queue
from butler.gateway.queue_settings import clear_session_override
from butler.human_gate import clear_session_gates
from butler.core.instruction_walkup import reset_instruction_claims
from butler.core.goal_loop import clear_state as clear_goal_loop
from butler.core.compaction_checkpoint import clear_checkpoint


def format_project_switch_brief_safe(
    orchestrator: Any,
    session_key: str,
    project_name: str,
) -> str:
    def _run() -> str:

        return str(
            format_project_switch_brief(orchestrator, session_key, project_name) or ""
        )

    result = safe_best_effort(
        _run,
        label="dialog_commands.switch_brief",
        default="",
    )
    return str(result or "")


def format_project_slug_hint_safe(available: list[Any]) -> str:
    def _run() -> str:
        slug_map = [
            f"{p.workspace.name}→{p.name}"
            for p in available
            if getattr(p, "workspace", None)
        ]
        if slug_map:
            return f"\n目录名对照: {', '.join(slug_map[:6])}"
        return ""

    result = safe_best_effort(
        _run,
        label="dialog_commands.slug_hint",
        default="",
    )
    return str(result or "")


def record_session_reset_safe(session_key: str, *, reason: str) -> None:
    def _run() -> None:

        record_session_reset(session_key, reason=reason)

    safe_best_effort(_run, label="dialog_commands.session_reset", default=None)


def cleanup_new_session_state_safe(session_key: str) -> None:
    def _run() -> None:

        reset_hook_telemetry(session_key)
        reset_completion_telemetry(session_key)

        reset_read_state(session_key)
        reset_queue(session_key)
        clear_session_override(session_key)
        clear_session_gates(session_key)
        reset_instruction_claims(session_key=session_key)

        clear_goal_loop(session_key)
        clear_checkpoint(session_key)

    safe_best_effort(_run, label="dialog_commands.new_session_cleanup", default=None)
