"""System prompt template best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def skill_summary_disclaimer_lines_safe() -> list[str]:
    def _run() -> list[str]:
        from butler.skills.injection_policy import skill_summary_disclaimer

        disclaimer = skill_summary_disclaimer()
        if not disclaimer:
            return []
        return [disclaimer, ""]

    result = safe_best_effort(
        _run,
        label="templates.skill_disclaimer",
        default=[],
    )
    return list(result) if isinstance(result, list) else []
