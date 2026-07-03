"""Eval feedback experience lifecycle best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def apply_experience_lifecycle_action_safe(report: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(action, error)``; ``error`` set when lifecycle apply fails."""
    try:
        from butler.dev_engine.coding_knowledge import ExperienceLibrary, TheoremLibrary
        from butler.config import get_butler_home

        path = get_butler_home() / "coding_experiences.json"
        tlib = TheoremLibrary()
        xlib = ExperienceLibrary.load_from_file(str(path), theorem_lib=tlib)
        if xlib.count == 0:
            return {"action": "experience_lifecycle", "skipped": "empty_library"}, None

        critical = [s for s in report.suggestions if s.severity == "critical"]
        if not critical:
            return {"action": "experience_lifecycle", "skipped": "no_critical"}, None

        candidates = sorted(
            xlib._experiences.items(),
            key=lambda item: item[1].validity_end,
        )[:3]
        if not candidates:
            return {"action": "experience_lifecycle", "skipped": "no_candidates"}, None
        eval_results = {eid: False for eid, _ in candidates}
        result = xlib.lifecycle_pass(eval_results)
        result["demoted_ids"] = list(eval_results.keys())
        xlib.save_to_file(str(path))
        return {"action": "experience_lifecycle", **result}, None
    except Exception as exc:
        logger.debug("experience lifecycle action skipped: %s", exc)
        return None, str(exc)
