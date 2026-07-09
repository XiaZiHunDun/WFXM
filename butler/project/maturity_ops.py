"""Best-effort hooks to update project maturity counters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.project.maturity import (
    project_for_resolved_path,
    record_dev_delegate_run,
    record_lines_modified,
)


def _line_delta_for_write(content: str) -> int:
    text = content or ""
    if not text.strip():
        return 1
    return max(1, len(text.splitlines()))


def _line_delta_for_patch(old_string: str, new_string: str) -> int:
    old_lines = (old_string or "").splitlines()
    new_lines = (new_string or "").splitlines()
    return max(1, abs(len(new_lines) - len(old_lines)) or len(new_lines))


def record_edit_maturity_safe(
    tool_name: str,
    args: dict[str, Any],
    *,
    resolved_path: Path | None = None,
) -> None:
    def _run() -> None:
        path = resolved_path
        if path is None:
            raw = str(args.get("path") or "").strip()
            if not raw:
                return
            path = Path(raw).expanduser()
            if not path.is_absolute():
                from butler.tools.path_safety import tool_safe_root

                path = tool_safe_root() / path
        try:
            resolved = path.resolve(strict=False)
        except OSError:
            return
        project_name = project_for_resolved_path(resolved)
        if not project_name:
            return
        name = str(tool_name or "")
        if name == "write_file":
            delta = _line_delta_for_write(str(args.get("content") or ""))
        elif name == "patch":
            delta = _line_delta_for_patch(
                str(args.get("old_string") or ""),
                str(args.get("new_string") or ""),
            )
        else:
            return
        record_lines_modified(project_name, delta)

    safe_best_effort(_run, label="maturity.record_edit", default=None)


def record_dev_delegate_maturity_safe(project_name: str, role: str) -> None:
    def _run() -> None:
        r = str(role or "").strip().lower()
        if r not in ("dev", "development", "dev_agent", "developer"):
            return
        record_dev_delegate_run(project_name)

    safe_best_effort(_run, label="maturity.record_dev_delegate", default=None)


__all__ = ["record_dev_delegate_maturity_safe", "record_edit_maturity_safe"]
