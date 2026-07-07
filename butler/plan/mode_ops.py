"""Plan mode best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def load_plan_prompt_from_paths(candidates: tuple[Path, ...]) -> str:
    for path in candidates:
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return ""


def append_plan_graph_appendix_safe(body: str) -> str:
    def _run() -> str:
        from butler.core.reasoning_trace import get_plan_mode_graph_appendix

        return str(body + get_plan_mode_graph_appendix())

    result = safe_best_effort(
        _run,
        label="plan_mode.graph_appendix",
        default=body,
    )
    return str(result or body)


def save_plan_mode_flag_safe(session_key: str, enabled: bool) -> None:
    def _run() -> None:
        from butler.plan.store import save_plan_mode_flag

        save_plan_mode_flag(session_key, enabled)

    safe_best_effort(_run, label="plan_mode.save_flag", default=None)


def record_plan_mode_enabled_safe(session_key: str) -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_plan_step

        record_plan_step(session_key, title="plan_mode_enabled", phase="start")

    safe_best_effort(_run, label="plan_mode.record_step", default=None)


def load_plan_mode_flag_safe(session_key: str) -> bool:
    def _run() -> bool:
        from butler.plan.store import load_plan_mode_flag

        return bool(load_plan_mode_flag(session_key))

    result = safe_best_effort(
        _run,
        label="plan_mode.load_flag",
        default=False,
    )
    return bool(result)


def resolve_session_key_safe(session_key: str) -> str:
    key = str(session_key or "").strip()
    if key:
        return key

    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip() or "default"

    result = safe_best_effort(
        _run,
        label="plan_mode.session_key",
        default="default",
    )
    return str(result or "default")
