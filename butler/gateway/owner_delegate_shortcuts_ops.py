"""Owner delegate shortcut best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import cast

from butler.core.best_effort import safe_best_effort


def recent_read_paths_safe(session_key: str, *, limit: int = 5) -> list[str]:
    def _run() -> list[str]:
        from butler.core.session_tool_index import list_session_read_files

        return cast(list[str], list_session_read_files(session_key, limit=limit))

    result = safe_best_effort(
        _run,
        label="owner_delegate_shortcuts.read_paths",
        default=[],
    )
    return list(result) if isinstance(result, list) else []


def cc_bridge_enabled_safe() -> bool:
    def _run() -> bool:
        from butler.runtime.cc_bridge import cc_bridge_enabled

        return bool(cc_bridge_enabled())

    result = safe_best_effort(
        _run,
        label="owner_delegate_shortcuts.cc_bridge_flag",
        default=False,
    )
    return bool(result)
