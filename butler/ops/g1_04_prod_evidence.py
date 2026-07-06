"""G1-04 production-sourced eval_feedback rows (non-B9 triggers)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)

_STATE_NAME = "g1_04_prod_evidence_state.json"
_DEDUPE_SECONDS = 6 * 3600


def prod_evidence_enabled() -> bool:
    return os.getenv("BUTLER_EVAL_PROD_EVIDENCE", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _state_path() -> Path:
    from butler.config import get_butler_home

    return cast(Path, get_butler_home()) / "config" / _STATE_NAME


def _dedupe_key(
    *,
    project: str,
    task_preview: str,
    event: str,
) -> str:
    raw = f"{project}:{event}:{task_preview[:160]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _should_dedupe(key: str) -> bool:
    path = _state_path()
    if not path.is_file():
        return False
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        last = float((state.get("keys") or {}).get(key) or 0.0)
        return (time.time() - last) < _DEDUPE_SECONDS
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False


def _mark_dedupe(key: str) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {}
    if path.is_file():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
    keys = dict(state.get("keys") or {})
    keys[key] = time.time()
    # prune old keys
    cutoff = time.time() - 7 * 86400
    keys = {k: v for k, v in keys.items() if float(v) > cutoff}
    state["keys"] = keys
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def record_g1_04_production_evidence(
    *,
    role: str = "dev",
    project: str = "",
    success: bool = False,
    verify_passed: bool | None = None,
    task_id: str = "",
    task_preview: str = "",
    failure_reason: str = "",
    capture_source: str = "delegate_pipeline",
    category: str = "",
    category_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append eval_feedback row with production trigger for G1-04 OT2 window."""
    if not prod_evidence_enabled():
        return {"recorded": False, "reason": "disabled"}
    if capture_source != "delegate_pipeline":
        return {"recorded": False, "reason": "not_delegate_pipeline"}

    from butler.ops.prod_experience_effectiveness import should_record_dev_delegate_outcome

    if not should_record_dev_delegate_outcome(
        role=role,
        category=category,
        category_meta=category_meta,
        task_preview=task_preview,
        task_id=task_id,
        project=project,
    ):
        return {"recorded": False, "reason": "not_production_delegate"}

    verify_failed = verify_passed is False
    if success and verify_passed is not False:
        event = "verify_pass"
        trigger = "prod_delegate_verify_pass"
    else:
        event = "failure"
        trigger = "prod_delegate_failure"

    preview = (task_preview or task_id or "")[:200]
    dkey = _dedupe_key(project=project, task_preview=preview, event=event)
    if _should_dedupe(dkey):
        return {"recorded": False, "reason": "deduped", "trigger": trigger}

    record: dict[str, Any] = {
        "action": "record_production_evidence",
        "trigger": trigger,
        "project": project,
        "role": role,
        "success": bool(success),
        "verify_passed": verify_passed,
        "task_id": task_id,
        "task_preview": preview,
        "failure_reason": (failure_reason or "")[:200],
        "capture_source": capture_source,
    }
    from butler.ops.g1_04_prod_evidence_ops import append_production_evidence_safe

    ok, err = append_production_evidence_safe(record)
    if not ok:
        return {"recorded": False, "reason": err or "unknown"}
    _mark_dedupe(dkey)
    logger.info("G1-04 production evidence recorded trigger=%s project=%s", trigger, project)
    return {"recorded": True, "trigger": trigger, "event": event}


__all__ = ["prod_evidence_enabled", "record_g1_04_production_evidence"]
