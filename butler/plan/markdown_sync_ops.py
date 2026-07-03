"""Plan markdown sync best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import PurePosixPath

from butler.core.best_effort import safe_best_effort
from butler.plan.markdown_sync import extract_plan_steps_from_markdown

logger = logging.getLogger(__name__)


def sync_plan_file_to_transcript_safe(
    session_key: str,
    path: str,
    content: str,
) -> int:
    def _run() -> int:
        from butler.plan.mode import is_plan_mode, is_plan_writable_path

        if not is_plan_mode(session_key):
            return 0
        if not is_plan_writable_path(path):
            return 0
        from butler.core.session_transcript import record_plan_step

        steps = extract_plan_steps_from_markdown(content)
        if not steps:
            return 0
        name = PurePosixPath(str(path or "").replace("\\", "/")).name
        for step in steps:
            record_plan_step(
                session_key,
                title=step["title"],
                phase="sync",
                detail=step.get("detail") or "",
                assumption=step.get("assumption") or "",
                evidence=step.get("evidence") or "",
                step_kind=step.get("step_kind") or "step",
            )
        logger.debug("plan markdown sync: %s (%d steps)", name, len(steps))
        return len(steps)

    result = safe_best_effort(
        _run,
        label="plan_markdown.sync_transcript",
        default=0,
    )
    return int(result) if isinstance(result, int) else 0
