"""Persist reflexion episodes to long-term experience (主线 H P2 subset)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)


def reflexion_write_enabled() -> bool:
    return env_truthy("BUTLER_REFLEXION_WRITE_EXPERIENCE", default=False)


def _experience_path() -> Path:
    try:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        pm = getattr(orch, "project_manager", None) if orch else None
        if pm is not None:
            proj = pm.get_current(session_key=str(get_current_session_key() or ""))
            if proj is not None:
                return (
                    Path(proj.workspace).expanduser().resolve()
                    / ".butler"
                    / "experiences"
                    / "reflexion.jsonl"
                )
    except Exception:
        pass
    return Path.home() / ".butler" / "experiences" / "reflexion.jsonl"


def write_reflexion_experience(
    *,
    tool_name: str,
    failure_count: int,
    last_error: str = "",
    session_key: str = "",
) -> None:
    if not reflexion_write_enabled() or failure_count < 2:
        return
    path = _experience_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": str(tool_name or "")[:64],
        "failure_count": int(failure_count),
        "error": str(last_error or "")[:400],
        "session_key": str(session_key or "")[:120],
        "kind": "reflexion",
    }
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.debug("reflexion write skipped: %s", exc)


__all__ = ["reflexion_write_enabled", "write_reflexion_experience"]
