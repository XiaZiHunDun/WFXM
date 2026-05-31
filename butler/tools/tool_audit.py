"""Tool audit recording, result finalization, and observation tracking."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

_TOOL_AUDIT_EVENTS: deque[dict[str, Any]] = deque(maxlen=200)
_TOOL_AUDIT_EVENTS_BY_SESSION: dict[str, deque[dict[str, Any]]] = {}
_TOOL_AUDIT_LOCK = threading.RLock()


def _parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _tool_result_ok(payload: dict[str, Any]) -> bool:
    if payload.get("ok") is False:
        return False
    if "error" in payload:
        return False
    if payload.get("success") is False:
        return False
    exit_code = payload.get("exit_code")
    if isinstance(exit_code, int) and exit_code != 0:
        return False
    return True


def _tool_result_code(name: str, payload: dict[str, Any], *, ok: bool) -> str:
    if ok:
        return "TOOL_OK"
    guardrail = payload.get("guardrail")
    if isinstance(guardrail, dict):
        action = guardrail.get("action")
        if action == "halt":
            return "TOOL_GUARDRAIL_HALT"
        if action == "block":
            return "TOOL_GUARDRAIL_BLOCKED"
    if payload.get("code"):
        return str(payload["code"])
    error = str(payload.get("error") or "")
    if error == "interrupted":
        return "TOOL_INTERRUPTED"
    if isinstance(payload.get("exit_code"), int) and payload["exit_code"] != 0:
        return "TOOL_EXIT_NONZERO"
    from butler.tools.registry import _REGISTRY

    if name not in _REGISTRY:
        return "TOOL_NOT_FOUND"
    lowered = error.lower()
    if (
        "access denied" in lowered
        or "outside workspace" in lowered
        or "路径在工作区外" in error
        or "sensitive" in lowered
        or "symlink" in lowered
        or "hardlinked" in lowered
    ):
        return "TOOL_SECURITY_DENIED"
    if lowered.startswith("file not found") or lowered.startswith("unknown tool"):
        return "TOOL_NOT_FOUND"
    if "timeout" in lowered or "timed out" in lowered:
        return "TOOL_TIMEOUT"
    if "too large" in lowered or "limit" in lowered:
        return "TOOL_RESOURCE_LIMIT"
    return "TOOL_ERROR"


def _record_tool_audit(
    name: str,
    args: dict,
    *,
    ok: bool,
    code: str,
    started_at: float,
) -> None:
    try:
        from butler.execution_context import get_audit_session_key

        session_key = get_audit_session_key()
    except Exception:
        session_key = "unscoped"
    event = {
        "tool": name,
        "ok": ok,
        "code": code,
        "session_key": session_key or "",
        "elapsed_ms": round((time.monotonic() - started_at) * 1000, 2),
        "arg_keys": sorted(str(key) for key in (args or {}).keys()),
    }
    with _TOOL_AUDIT_LOCK:
        _TOOL_AUDIT_EVENTS.append(event)
        bucket = _TOOL_AUDIT_EVENTS_BY_SESSION.setdefault(
            event["session_key"],
            deque(maxlen=200),
        )
        bucket.append(event)


def get_tool_audit_events(
    limit: int | None = None,
    *,
    session_key: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent tool audit events with redacted arguments."""
    with _TOOL_AUDIT_LOCK:
        if session_key is None:
            events = list(_TOOL_AUDIT_EVENTS)
        else:
            events = list(_TOOL_AUDIT_EVENTS_BY_SESSION.get(session_key, ()))
    if limit is not None:
        events = events[-max(0, int(limit)):]
    return [dict(event) for event in events]


def reset_tool_audit_events(session_key: str | None = None) -> None:
    """Clear in-memory tool audit events. Intended for tests and diagnostics reset."""
    with _TOOL_AUDIT_LOCK:
        if session_key is None:
            _TOOL_AUDIT_EVENTS.clear()
            _TOOL_AUDIT_EVENTS_BY_SESSION.clear()
            return
        _TOOL_AUDIT_EVENTS_BY_SESSION.pop(session_key, None)
        retained = [
            event for event in _TOOL_AUDIT_EVENTS
            if event.get("session_key") != session_key
        ]
        _TOOL_AUDIT_EVENTS.clear()
        _TOOL_AUDIT_EVENTS.extend(retained[-_TOOL_AUDIT_EVENTS.maxlen:])


def pop_last_tool_audit_for_tool(name: str) -> None:
    """Remove the latest audit event for a tool when replacing it with guardrail halt."""
    with _TOOL_AUDIT_LOCK:
        if not _TOOL_AUDIT_EVENTS or _TOOL_AUDIT_EVENTS[-1].get("tool") != name:
            return
        last = _TOOL_AUDIT_EVENTS.pop()
        session_key = str(last.get("session_key") or "")
        bucket = _TOOL_AUDIT_EVENTS_BY_SESSION.get(session_key)
        if bucket and bucket[-1].get("tool") == name:
            bucket.pop()


def _maybe_record_tool_observation(
    name: str,
    args: dict,
    payload: dict[str, Any],
) -> None:
    try:
        from butler.execution_context import get_current_session_key
        from butler.core.session_transcript import record_tool_observation

        sk = str(get_current_session_key() or "").strip()
        if not sk:
            return
        preview = ""
        if payload.get("error"):
            preview = str(payload.get("error") or "")[:200]
        elif payload.get("mode") == "summary":
            preview = f"summary lines={payload.get('total_lines', '?')}"
        elif payload.get("preview"):
            preview = str(payload.get("preview") or "")[:200]
        else:
            for key in ("content", "result", "output", "message"):
                if payload.get(key):
                    preview = str(payload[key])[:200]
                    break
        if not preview and name == "read_file":
            preview = str(args.get("path") or "")[:120]
        record_tool_observation(
            sk,
            tool=name,
            ok=_tool_result_ok(payload),
            preview=preview,
        )
        try:
            from butler.memory.observer_queue import enqueue_tool_observation
            from butler.execution_context import get_current_orchestrator

            path_hint = str(args.get("path") or args.get("file") or "")
            workspace = None
            orch = get_current_orchestrator()
            if orch is not None:
                try:
                    proj = orch.project_manager.get_current(session_key=sk)
                    if proj is not None:
                        from pathlib import Path

                        workspace = Path(proj.workspace)
                except Exception:
                    workspace = None
            enqueue_tool_observation(
                session_key=sk,
                tool=name,
                ok=_tool_result_ok(payload),
                preview=preview,
                path=path_hint,
                workspace=workspace,
            )
        except Exception as exc:
            logger.debug("maybe record tool observation skipped: %s", exc)
    except Exception as exc:
        logger.debug("maybe record tool observation skipped: %s", exc)


def _finalize_tool_result(
    name: str,
    args: dict,
    result: Any,
    *,
    started_at: float,
) -> str:
    if isinstance(result, str):
        payload = _parse_json_object(result)
        if payload is None:
            ok = True
            code = "TOOL_OK"
            _record_tool_audit(name, args, ok=ok, code=code, started_at=started_at)
            parsed = _parse_json_object(result)
            if isinstance(parsed, dict):
                _maybe_record_tool_observation(name, args, parsed)
            elif name:
                _maybe_record_tool_observation(
                    name,
                    args,
                    {"preview": str(result)[:200]},
                )
            return result
    elif isinstance(result, dict):
        payload = dict(result)
    else:
        payload = result

    if isinstance(payload, dict):
        ok = _tool_result_ok(payload)
        code = _tool_result_code(name, payload, ok=ok)
        if not ok:
            payload.setdefault("ok", False)
            payload.setdefault("tool", name)
            payload.setdefault("code", code)
            err = str(payload.get("error") or "")
            if err.startswith("Access denied"):
                try:
                    from butler.hooks.runner import run_permission_denied_hooks

                    hint = run_permission_denied_hooks(name, args, err)
                    if hint:
                        payload["permission_denied_hint"] = hint
                except Exception as exc:
                    logger.debug("PermissionDenied hooks skipped: %s", exc)
        _record_tool_audit(name, args, ok=ok, code=code, started_at=started_at)
        _maybe_record_tool_observation(name, args, payload)
        return json.dumps(payload, ensure_ascii=False, default=str)

    _record_tool_audit(name, args, ok=True, code="TOOL_OK", started_at=started_at)
    if isinstance(payload, dict):
        _maybe_record_tool_observation(name, args, payload)
    return json.dumps(payload, ensure_ascii=False, default=str)


def finalize_tool_result(
    name: str,
    args: dict,
    result: Any,
    *,
    started_at: float | None = None,
) -> str:
    """Apply Butler's tool result envelope and audit record to fallback paths."""
    return _finalize_tool_result(
        name,
        args,
        result,
        started_at=started_at if started_at is not None else time.monotonic(),
    )
