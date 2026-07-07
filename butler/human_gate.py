"""Human-in-the-loop gates for WeChat (workflow step approval, zero deps)."""

from __future__ import annotations

from butler.env_parse import float_env
import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from butler.config import get_butler_home
from butler.io.safe_load import safe_load_json
from butler.human_gate_ops import auto_resume_workflow_safe
from butler.io.atomic_write import atomic_write_text
from butler.gateway.gate_reply_templates import injection_gate_pending_hint, workflow_gate_pending_hint
from butler.gateway.gate_reply_templates import injection_gate_confirmed_hint
from butler.gateway.gate_reply_templates import workflow_gate_confirmed_hint
from butler.human_gate_ops import workflow_auto_resume_reply_safe

logger = logging.getLogger(__name__)

_gate_lock = threading.Lock()


def _workflow_auto_resume_enabled() -> bool:
    return os.getenv("BUTLER_WORKFLOW_AUTO_RESUME", "").strip() == "1"


def _auto_resume_workflow(session_key: str, workflow_name: str) -> str | None:
    """Re-run the workflow after approval, returning the result text."""

    return cast(str | None, auto_resume_workflow_safe(session_key, workflow_name))


def _gate_ttl_seconds() -> float:
    import os

    try:
        return float(float_env("BUTLER_GATEWAY_HUMAN_GATE_TTL", 3600, min=60.0))
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
    path = Path(get_butler_home()) / "human_gates"
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
    # Audit R2-19: corrupt gate file used to silently return None,
    # which causes check_workflow_step_approval to create a fresh gate
    # on every retry — Owner never sees the "already asked" state.
    # safe_load_json renames the corrupt file for forensic retention,
    # logs WARNING with exc_info, and records the event for /诊断.
    data = safe_load_json(path, default=None, kind="human_gate_pending")
    if not isinstance(data, dict):
        return None
    try:
        raw_created = data.get("created_at")
        created_at = float(raw_created) if raw_created else 0.0
    except (TypeError, ValueError) as exc:
        logger.warning(
            "human gate schema invalid (created_at): %s", exc,
            exc_info=exc,
        )
        return None
    gate = PendingGate(
        kind=str(data.get("kind") or ""),
        workflow=str(data.get("workflow") or ""),
        step_id=str(data.get("step_id") or ""),
        created_at=created_at,
    )
    if _is_gate_expired(gate.created_at):
        _save_pending(session_key, None)
        return None
    return gate


def _save_pending(session_key: str, gate: PendingGate | None) -> None:
    path = _gate_path(session_key)
    if gate is None:
        path.unlink(missing_ok=True)
        return

    atomic_write_text(path, json.dumps(gate.to_dict(), ensure_ascii=False, indent=2))


def _load_approved(session_key: str) -> set[str]:
    path = _approved_path(session_key)
    # Audit R2-19: corrupt approved-list file used to silently fall
    # back to empty set (losing Owner's prior /approve grants). safe_load
    # renames the corrupt file for forensic retention, logs WARNING with
    # exc_info, and records the event for /诊断.
    data = safe_load_json(path, default=None, kind="human_gate_approved")
    if isinstance(data, list):
        return {str(x) for x in data}
    if isinstance(data, dict):
        return {str(k) for k, v in data.items() if v}
    return set()


def _save_approved(session_key: str, keys: set[str]) -> None:
    path = _approved_path(session_key)
    if not keys:
        path.unlink(missing_ok=True)
        return

    atomic_write_text(path, json.dumps(sorted(keys), ensure_ascii=False, indent=2))


def _approval_key(workflow: str, step_id: str) -> str:
    return f"{workflow}::{step_id}"


def is_step_approved(session_key: str, workflow: str, step_id: str) -> bool:
    with _gate_lock:
        return _approval_key(workflow, step_id) in _load_approved(session_key)


def mark_step_approved(session_key: str, workflow: str, step_id: str) -> None:
    with _gate_lock:
        keys = _load_approved(session_key)
        keys.add(_approval_key(workflow, step_id))
        _save_approved(session_key, keys)


def clear_session_gates(session_key: str) -> None:
    with _gate_lock:
        _save_pending(session_key, None)
        _save_approved(session_key, set())


def has_pending_gate(session_key: str) -> bool:
    with _gate_lock:
        return _load_pending(session_key) is not None


def has_injection_review_pending(session_key: str) -> bool:
    with _gate_lock:
        pending = _load_pending(session_key)
        return pending is not None and pending.kind == "injection_review"


def check_workflow_step_approval(
    session_key: str,
    workflow_name: str,
    step_id: str,
) -> bool:
    """Return True to run the step; False waits for 确认/取消 on WeChat."""
    sk = str(session_key or "").strip()
    with _gate_lock:
        if _approval_key(workflow_name, step_id) in _load_approved(sk):
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

    with _gate_lock:
        pending = _load_pending(session_key)
    if pending is None:
        return ""
    if pending.kind == "injection_review":
        return str(injection_gate_pending_hint(score=pending.step_id))
    return str(
        workflow_gate_pending_hint(
            workflow=pending.workflow,
            step_id=pending.step_id,
        )
    )


def request_injection_review_gate(session_key: str, *, score: int) -> None:
    """Owner must 确认 before retrying a high-risk inbound message."""
    sk = str(session_key or "").strip()
    with _gate_lock:
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

        atomic_write_text(path, json.dumps(payload))
    except OSError as exc:
        logger.debug("injection bypass write failed: %s", exc)


def consume_injection_bypass(session_key: str) -> bool:
    """Atomically consume a one-shot injection bypass across processes.

    Sprint 16 REL-11-7: 旧实现用进程内 ``threading.Lock`` + 预检
    + ``unlink(missing_ok=True)`` 模式, 跨进程可多个 consumer 都
    返回 True, 单次性失效。

    改用 ``os.rename`` 做原子抢占 — POSIX 保证原子; 失败方收到
    ``FileNotFoundError`` 即知自己输了比赛, 返回 ``False``。
    """
    path = _injection_bypass_path(session_key)
    consumed_path = path.with_name(path.name + ".consumed")
    # 原子抢占: 多个进程并发, 仅 1 个 rename 成功。
    try:
        os.rename(path, consumed_path)
    except FileNotFoundError:
        return False

    # 抢占成功, 读取内容判断是否过期
    # Audit R2-19: corrupt consumed-bypass file used to silently
    # return False, masking the issue. safe_load_json renames the
    # corrupt file for forensic retention, logs WARNING with exc_info,
    # and records the event for /诊断.
    data = safe_load_json(consumed_path, default=None, kind="human_gate_injection_bypass")
    if not isinstance(data, dict):
        return False
    try:
        expires = float(data.get("expires_at") or 0)
    except (TypeError, ValueError):
        return False
    if expires < time.time():
        try:
            consumed_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    return True


def resolve_human_gate_message(
    session_key: str,
    text: str,
    *,
    owner_verified: bool = False,
) -> str | None:
    """Consume 确认/取消 for a pending gate; return user-visible reply or None.

    ``owner_verified`` must be set to ``True`` by the caller after
    confirming gateway-owner identity.  When ``False`` (default) the
    function refuses to grant any approval — fail-closed per T6.
    """
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

        # T6 fail-closed: confirm/approve requires owner verification.
        if not owner_verified:
            logger.warning(
                "resolve_human_gate_message: approval attempt without owner "
                "verification (session=%s) — rejected",
                session_key,
            )
            return "⛔ 确认操作需要 Owner 身份验证。"

        if pending.kind == "injection_review":
            grant_injection_bypass(session_key)
            _save_pending(session_key, None)

            return str(injection_gate_confirmed_hint(score=pending.step_id))

        keys = _load_approved(session_key)
        keys.add(_approval_key(pending.workflow, pending.step_id))
        _save_approved(session_key, keys)
        wf_name = pending.workflow
        step_id = pending.step_id
        _save_pending(session_key, None)

    if _workflow_auto_resume_enabled():

        resumed = workflow_auto_resume_reply_safe(
            session_key,
            wf_name,
            step_id,
            enabled=True,
            resume_fn=_auto_resume_workflow,
            confirmed_hint_fn=workflow_gate_confirmed_hint,
        )
        if resumed:
            return str(resumed)


    return str(
        workflow_gate_confirmed_hint(
            workflow=wf_name, auto_resumed=False, step_id=step_id
        )
    )
