"""WeChat scenario sim best-effort / fail-closed helpers (P0-A)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from butler.core.best_effort import safe_best_effort


def delegate_enrichment_imports_ready() -> bool:
    def _run() -> bool:
        from butler.core.session_epoch import load_epoch_transcript_rows  # noqa: F401
        from butler.report import get_last_report  # noqa: F401

        return True

    result = safe_best_effort(
        _run,
        label="wechat_scenario_sim.delegate_imports",
        default=False,
    )
    return bool(result)


def run_scenario_case_safe(
    run_case: Callable[[], None],
    entry: Any,
    *,
    t0: float,
) -> None:
    try:
        run_case()
    except Exception as exc:
        entry.ok = False
        entry.errors.append(str(exc)[:200])
        entry.elapsed_seconds = time.time() - t0
