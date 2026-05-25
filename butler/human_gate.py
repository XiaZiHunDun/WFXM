"""Human-in-the-loop gates for WeChat (workflow step approval, zero deps)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from butler.config import get_butler_home

logger = logging.getLogger(__name__)


def _gate_ttl_seconds() -> float:
    import os

    try:
        return max(60.0, float(os.getenv("BUTLER_GATEWAY_HUMAN_GATE_TTL", "3600")))
    except ValueError:
        return 3600.0


def _is_gate_expired(created_at: float) -> bool:
    if created_at <= 0:
        return False
    import time

    return (time.time() - created_at) > _gate_ttl_seconds()


_CONFIRM = frozenset({
    "确认",
    "确认继续",
    "继续",
    "yes",
    "y",
    "ok",
    "/确认",
    "/approve",
})
_CANCEL = frozenset({
    "取消",
    "中止",
    "停止",
    "no",
    "n",
    "/取消",
    "/cancel",
})


@dataclass
class PendingGate:
    kind: str
    workflow: str
    step_id: str
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _gate_dir() -> Path:
    path = get_butler_home() / "human_gates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _gate_path(session_key: str) -> Path:
    import hashlib

    digest = hashlib.sha256(str(session_key or "default").encode("utf-8")).hexdigest()[:16]
    return _gate_dir() / f"{digest}.json"


def _approved_path(session_key: str) -> Path:
    import hashlib

    digest = hashlib.sha256(str(session_key or "default").encode("utf-8")).hexdigest()[:16]
    return _gate_dir() / f"{digest}.approved.json"


def _load_pending(session_key: str) -> PendingGate | None:
    path = _gate_path(session_key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        gate = PendingGate(
            kind=str(data.get("kind") or ""),
            workflow=str(data.get("workflow") or ""),
            step_id=str(data.get("step_id") or ""),
            created_at=float(data.get("created_at") or 0),
        )
        if _is_gate_expired(gate.created_at):
            _save_pending(session_key, None)
            return None
        return gate
    except Exception as exc:
        logger.debug("human gate read failed: %s", exc)
        return None


def _save_pending(session_key: str, gate: PendingGate | None) -> None:
    path = _gate_path(session_key)
    if gate is None:
        path.unlink(missing_ok=True)
        return
    path.write_text(json.dumps(gate.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def _load_approved(session_key: str) -> set[str]:
    path = _approved_path(session_key)
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(x) for x in data}
        if isinstance(data, dict):
            return {str(k) for k, v in data.items() if v}
    except Exception:
        pass
    return set()


def _save_approved(session_key: str, keys: set[str]) -> None:
    path = _approved_path(session_key)
    if not keys:
        path.unlink(missing_ok=True)
        return
    path.write_text(json.dumps(sorted(keys), ensure_ascii=False, indent=2), encoding="utf-8")


def _approval_key(workflow: str, step_id: str) -> str:
    return f"{workflow}::{step_id}"


def is_step_approved(session_key: str, workflow: str, step_id: str) -> bool:
    return _approval_key(workflow, step_id) in _load_approved(session_key)


def mark_step_approved(session_key: str, workflow: str, step_id: str) -> None:
    keys = _load_approved(session_key)
    keys.add(_approval_key(workflow, step_id))
    _save_approved(session_key, keys)


def clear_session_gates(session_key: str) -> None:
    _save_pending(session_key, None)
    _save_approved(session_key, set())


def has_pending_gate(session_key: str) -> bool:
    return _load_pending(session_key) is not None


def check_workflow_step_approval(
    session_key: str,
    workflow_name: str,
    step_id: str,
) -> bool:
    """Return True to run the step; False waits for 确认/取消 on WeChat."""
    sk = str(session_key or "").strip()
    if is_step_approved(sk, workflow_name, step_id):
        return True
    pending = _load_pending(sk)
    if pending is not None:
        if pending.workflow == workflow_name and pending.step_id == step_id:
            return False
    _save_pending(
        sk,
        PendingGate(
            kind="workflow_step",
            workflow=workflow_name,
            step_id=step_id,
            created_at=time.time(),
        ),
    )
    return False


def format_pending_hint(session_key: str) -> str:
    pending = _load_pending(session_key)
    if pending is None:
        return ""
    return (
        f"工作流「{pending.workflow}」步骤「{pending.step_id}」等待确认。"
        "回复「确认」继续（随后请再次发送 /workflow），或「取消」中止。"
    )


def resolve_human_gate_message(session_key: str, text: str) -> str | None:
    """Consume 确认/取消 for a pending gate; return user-visible reply or None."""
    stripped = (text or "").strip()
    if stripped not in _CONFIRM and stripped not in _CANCEL:
        return None

    pending = _load_pending(session_key)
    if pending is None:
        return None

    if stripped in _CANCEL:
        _save_pending(session_key, None)
        return f"已取消工作流步骤「{pending.step_id}」（{pending.workflow}）。"

    mark_step_approved(session_key, pending.workflow, pending.step_id)
    _save_pending(session_key, None)
    return (
        f"已确认步骤「{pending.step_id}」。"
        f"请再次发送 /workflow {pending.workflow} 以继续执行该步骤及后续节点。"
    )
