"""Fork session transcript from the Nth user message (Codex thread_manager subset)."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from butler.core.session_transcript import transcript_path

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()

_USER_TYPES = frozenset({"user"})


def fork_transcript_at_user_message(
    session_key: str,
    *,
    keep_from_user_index: int = 1,
) -> dict[str, Any]:
    """
    Keep JSONL lines from the Nth ``type=user`` row onward (1-based).
    Prepends a ``transcript_fork`` marker. Does not change in-memory agent messages.
    """
    sk = str(session_key or "").strip()
    if not sk:
        return {"ok": False, "error": "empty_session_key"}
    idx = max(1, int(keep_from_user_index))

    path = transcript_path(sk)
    if not path.is_file():
        return {"ok": False, "error": "transcript_missing", "path": str(path)}

    with _LOCK:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

        user_seen = 0
        cut_line = -1
        for i, ln in enumerate(lines):
            try:
                row = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if str(row.get("type") or "") in _USER_TYPES:
                user_seen += 1
                if user_seen == idx:
                    cut_line = i
                    break

        if cut_line < 0:
            return {
                "ok": False,
                "error": "user_index_not_found",
                "requested_user_index": idx,
                "user_messages_found": user_seen,
            }

        if cut_line == 0:
            return {
                "ok": True,
                "skipped": True,
                "reason": "already_at_first_user",
                "lines_before": len(lines),
                "lines_after": len(lines),
                "user_index": idx,
            }

        dropped = cut_line
        tail = lines[cut_line:]
        marker = {
            "type": "transcript_fork",
            "ts": datetime.now(timezone.utc).isoformat(),
            "keep_from_user_index": idx,
            "dropped_lines": dropped,
            "kept_lines": len(tail),
        }
        try:
            from butler.core.transcript_index import invalidate_index

            invalidate_index(path)
            with path.open("w", encoding="utf-8") as fh:
                fh.write(json.dumps(marker, ensure_ascii=False) + "\n")
                for ln in tail:
                    fh.write(ln + "\n")
        except OSError as exc:
            logger.warning("Transcript fork failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "dropped_lines": dropped,
        "lines_before": len(lines),
        "lines_after": len(tail) + 1,
        "keep_from_user_index": idx,
        "path": str(path),
    }
