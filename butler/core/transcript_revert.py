"""Lightweight transcript truncate (OpenCode revert subset, no FS snapshot)."""

from __future__ import annotations

from butler.env_parse import int_env
import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

from butler.core.session_transcript import transcript_path

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()


def revert_keep_lines_default() -> int:
    try:
        return int_env("BUTLER_TRANSCRIPT_REVERT_KEEP_LINES", 40, min=5)
    except ValueError:
        return 40


def truncate_transcript(
    session_key: str,
    *,
    keep_last_lines: int | None = None,
) -> dict[str, Any]:
    """
    Keep the last N JSONL lines; prepend a revert marker row.
    Does not modify agent in-memory messages.
    """
    sk = str(session_key or "").strip()
    if not sk:
        return {"ok": False, "error": "empty_session_key"}
    keep = keep_last_lines if keep_last_lines is not None else revert_keep_lines_default()
    keep = max(1, int(keep))

    path = transcript_path(sk)
    if not path.is_file():
        return {"ok": False, "error": "transcript_missing", "path": str(path)}

    with _LOCK:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

        if len(lines) <= keep:
            return {
                "ok": True,
                "skipped": True,
                "reason": "already_within_limit",
                "lines_before": len(lines),
                "lines_after": len(lines),
            }

        dropped = len(lines) - keep
        tail = lines[-keep:]
        marker = {
            "type": "transcript_revert",
            "ts": datetime.now(timezone.utc).isoformat(),
            "dropped_lines": dropped,
            "kept_lines": keep,
        }
        try:
            from butler.core.transcript_index import invalidate_index

            invalidate_index(path)
            with path.open("w", encoding="utf-8") as fh:
                fh.write(json.dumps(marker, ensure_ascii=False) + "\n")
                for ln in tail:
                    fh.write(ln + "\n")
        except OSError as exc:
            logger.warning("Transcript revert failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "dropped_lines": dropped,
        "lines_before": len(lines),
        "lines_after": len(tail) + 1,
        "path": str(path),
    }
