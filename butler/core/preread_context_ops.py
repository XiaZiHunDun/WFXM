"""PreRead observation lookup best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def build_preread_observation_lines_safe(
    workspace: Path,
    file_path: str,
    *,
    limit: int = 3,
) -> list[str]:
    def _run() -> list[str]:
        from butler.memory.observer_queue import list_observations_for_path

        obs = list_observations_for_path(workspace, file_path, limit=limit)
        lines: list[str] = []
        for row in obs:
            preview = str(row.get("preview") or "").strip()
            tool = str(row.get("tool") or "")
            if preview:
                lines.append(f"- [{tool}] {preview[:160]}")
        return lines

    result = safe_best_effort(
        _run,
        label="preread_context.observations",
        default=[],
    )
    return list(result) if isinstance(result, list) else []
