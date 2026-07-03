"""Tool result path validation best-effort helpers (P0-A)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def is_readable_session_tool_result_path_safe(
    path_str: str,
    *,
    session_key: str,
    allowed_dir_for_session: Callable[[str], Path],
    current_session_key: Callable[[], str | None],
) -> bool:
    try:
        sk = str(session_key or current_session_key() or "").strip()
        if not sk:
            return False
        allowed_dir = allowed_dir_for_session(sk).resolve(strict=False)
        target = Path(path_str).expanduser().resolve(strict=False)
        if not target.is_file():
            return False
        return target.is_relative_to(allowed_dir)
    except Exception:
        return False
