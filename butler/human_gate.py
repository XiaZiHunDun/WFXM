"""Human-in-the-loop gates for WeChat (workflow step approval, zero deps)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from butler.config import get_butler_home

logger = logging.getLogger(__name__)

_gate_lock = threading.Lock()


def _workflow_auto_resume_enabled() -> bool:
    return os.getenv("BUTLER_WORKFLOW_AUTO_RESUME", "").strip() == "1"


def _auto_resume_workflow(session_key: str, workflow_name: str) -> str | None:
    """Re-run the workflow after approval, returning the result text."""
    try:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        if orch is None:
            return None
        pm = orch.project_manager
        proj = pm.get_current(session_key=session_key)
        if proj is None:
            return None
        from butler.workflows.runner import run_workflow_for_project

        return run_workflow_for_project(
            proj,
            workflow_name,
            session_key=session_key,
            orchestrator=orch,
        )
    except Exception as exc:
        logger.warning("Auto-resume workflow %s failed: %s", workflow_name, exc)
        return None


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
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    except Exception as exc:
        logger.warning("human gate read failed unexpectedly: %s", exc)
        return None


def _save_pending(session_key: str, gate: PendingGate | None) -> None:
    path = _gate_path(session_key)
    if gate is None:
        path.unlink(missing_ok=True)
        return
    from butler.io.atomic_write import atomic_write_text

    atomic_write_text(path, json.dumps(gate.to_dict(), ensure_ascii=False, indent=2))


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
    except Exception as exc:
        logger.debug("load approved skipped: %s", exc)
    return set()


def _save_approved(session_key: str, keys: set[str]) -> None:
    path = _approved_path(session_key)
    if not keys:
        path.unlink(missing_ok=True)
        return
    from butler.io.atomic_write import atomic_write_text

    atomic_write_text(path, json.dumps(sorted(keys), ensure_ascii=False, indent=2))


def _approval_key(workflow: str, step_id: str) -> str:
    return f"{workflow}::{step_id}"


def is_step_approved(session_key: str, workflow: str, step_id: str) -> bool:
    return _approval_key(workflow, step_id) in _load_approved(session_key)


def mark_step_approved(session_key: str, workflow: str, step_id: str) -> None:
    with _gate_lock:
        keys = _load_approved(session_key)
        keys.add(_approval_key(workflow, step_id))
        _save_approved(session_key, keys)


def clear_session_gates(session_key: str) -> None:
    _save_pending(session_key, None)
    _save_approved(session_key, set())


def has_pending_gate(session_key: str) -> bool:
    return _load_pending(session_key) is not None


def has_injection_review_pending(session_key: str) -> bool:
    pending = _load_pending(session_key)
    return pending is not None and pending.kind == "injection_review"


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
    if pending.kind == "injection_review":
        return (
            f"入站消息安全评分 {pending.step_id} 偏高，等待 Owner 确认。"
            "回复「确认」后请重发上一条消息，或「取消」忽略。"
        )
    return (
        f"工作流「{pending.workflow}」步骤「{pending.step_id}」等待确认。"
        "回复「确认」继续（随后请再次发送 /workflow），或「取消」中止。"
    )


def request_injection_review_gate(session_key: str, *, score: int) -> None:
    """Owner must 确认 before retrying a high-risk inbound message."""
    sk = str(session_key or "").strip()
    _save_pending(
        sk,
        PendingGate(
            kind="injection_review",
            workflow="",
            step_id=str(int(score)),
            created_at=time.time(),
        ),
    )


def _injection_bypass_path(session_key: str) -> Path:
    digest = hashlib.sha256(str(session_key or "default").encode()).hexdigest()[:16]
    return _gate_dir() / f"inj_bypass_{digest}.json"


def grant_injection_bypass(session_key: str, *, ttl_seconds: float = 300.0) -> None:
    """Allow one subsequent inbound to skip injection LLM block."""
    path = _injection_bypass_path(session_key)
    payload = {"expires_at": time.time() + min(max(30.0, ttl_seconds), 3600.0)}
    try:
        from butler.io.atomic_write import atomic_write_text

        atomic_write_text(path, json.dumps(payload))
    except OSError as exc:
        logger.debug("injection bypass write failed: %s", exc)


def consume_injection_bypass(session_key: str) -> bool:
    with _gate_lock:
        path = _injection_bypass_path(session_key)
        if not path.is_file():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            expires = float(data.get("expires_at") or 0)
        except (OSError, json.JSONDecodeError, TypeError):
            return False
        if expires < time.time():
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return False
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return True


def resolve_human_gate_message(session_key: str, text: str) -> str | None:
    """Consume 确认/取消 for a pending gate; return user-visible reply or None."""
    stripped = (text or "").strip()
    if stripped not in _CONFIRM and stripped not in _CANCEL:
        return None

    with _gate_lock:
        pending = _load_pending(session_key)
        if pending is None:
            return None

        if stripped in _CANCEL:
            _save_pending(session_key, None)
            if pending.kind == "injection_review":
                return "已取消高风险入站确认；请修改消息内容后重试。"
            return f"已取消工作流步骤「{pending.step_id}」（{pending.workflow}）。"

        if pending.kind == "injection_review":
            grant_injection_bypass(session_key)
            _save_pending(session_key, None)
            return (
                f"已确认入站安全评分 {pending.step_id}。"
                "请重新发送上一条消息以继续处理。"
            )

        keys = _load_approved(session_key)
        keys.add(_approval_key(pending.workflow, pending.step_id))
        _save_approved(session_key, keys)
        _save_pending(session_key, None)

    if _workflow_auto_resume_enabled():
        try:
            resume_reply = _auto_resume_workflow(session_key, pending.workflow)
            if resume_reply:
                return f"已确认步骤「{pending.step_id}」，自动继续执行…\n\n{resume_reply}"
        except Exception as exc:
            logger.warning("Workflow auto-resume failed: %s", exc)

    return (
        f"已确认步骤「{pending.step_id}」。"
        f"请再次发送 /workflow {pending.workflow} 以继续执行该步骤及后续节点。"
    )
