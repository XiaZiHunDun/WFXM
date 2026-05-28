"""Persist workflow pause snapshot for human_gate (Dify PauseState subset)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WorkflowPauseState:
    workflow: str
    step_id: str
    session_key: str
    execution_order: list[str]
    completed_steps: list[str]
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pause_path(session_key: str, workspace: Path | None = None) -> Path:
    if workspace is not None:
        return Path(workspace) / ".butler" / "workflow_pause.json"
    import hashlib

    from butler.config import get_butler_home

    digest = hashlib.sha256(str(session_key or "default").encode("utf-8")).hexdigest()[:16]
    return get_butler_home() / "workflow_pause" / f"{digest}.json"


def save_workflow_pause(
    state: WorkflowPauseState,
    *,
    workspace: Path | None = None,
) -> None:
    path = _pause_path(state.session_key, workspace)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.debug("workflow pause save failed: %s", exc)


def load_workflow_pause(
    session_key: str,
    *,
    workspace: Path | None = None,
) -> WorkflowPauseState | None:
    path = _pause_path(session_key, workspace)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return WorkflowPauseState(
        workflow=str(data.get("workflow") or ""),
        step_id=str(data.get("step_id") or ""),
        session_key=str(data.get("session_key") or session_key),
        execution_order=list(data.get("execution_order") or []),
        completed_steps=list(data.get("completed_steps") or []),
        created_at=float(data.get("created_at") or 0),
    )


def clear_workflow_pause(session_key: str, *, workspace: Path | None = None) -> None:
    path = _pause_path(session_key, workspace)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
