"""Read novel-factory workflow version from workflow_state.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT = "v3.0"
_PLACEHOLDER = "{workflow_version}"


def read_workflow_version(workspace: Path) -> str:
    """Return ``version`` field or default ``v3.0``."""
    path = Path(workspace).expanduser().resolve() / "novel-factory" / "workflow_state.json"
    if not path.is_file():
        return _DEFAULT
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ver = str((data or {}).get("version") or "").strip()
        return ver or _DEFAULT
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("workflow_state.json unreadable: %s", exc)
        return _DEFAULT


def resolve_job_command(command: list[str], workspace: Path) -> list[str]:
    """Replace ``{workflow_version}`` tokens in argv list."""
    if not command:
        return command
    ver = read_workflow_version(workspace)
    out: list[str] = []
    for part in command:
        s = str(part)
        if _PLACEHOLDER in s:
            s = s.replace(_PLACEHOLDER, ver)
        out.append(s)
    return out
