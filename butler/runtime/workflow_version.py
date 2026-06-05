"""Read novel-factory workflow version from workflow_state.json."""

from __future__ import annotations

import logging
from pathlib import Path

from butler.io.safe_load import safe_load_json

logger = logging.getLogger(__name__)

_DEFAULT = "v3.0"
_PLACEHOLDER = "{workflow_version}"


def read_workflow_version(workspace: Path) -> str:
    """Return ``version`` field or default ``v3.0``."""
    path = Path(workspace).expanduser().resolve() / "novel-factory" / "workflow_state.json"
    # Audit R2-19: corrupt workflow_state.json used to silently fall
    # back to default with a generic warning. safe_load_json
    # renames the corrupt file for forensic retention, logs WARNING
    # with exc_info, and records the event for /诊断.
    data = safe_load_json(path, default=None, kind="runtime_workflow_state")
    if not isinstance(data, dict):
        return _DEFAULT
    ver = str((data or {}).get("version") or "").strip()
    return ver or _DEFAULT


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
