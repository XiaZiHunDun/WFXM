"""Dev verify ACL conversion helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.contracts.dev_context_ports import DevVerifyView
from butler.core.best_effort import record_best_effort_skip

logger = logging.getLogger(__name__)


def _normalize_status(raw: Any) -> str:
    text = str(raw or "UNKNOWN").strip().upper()
    for candidate in ("PASS", "FAIL", "TIMEOUT", "SKIP", "UNKNOWN"):
        if text == candidate:
            return candidate
    if text in ("OK", "SUCCESS", "PASSED"):
        return "PASS"
    if text in ("ERROR", "FAILED"):
        return "FAIL"
    return "UNKNOWN"


def _diagnostics_from_any(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            out.append(
                {
                    "file": str(item.get("file") or ""),
                    "line": int(item.get("line") or 0),
                    "column": int(item.get("column") or 0),
                    "severity": str(item.get("severity") or "error"),
                    "message": str(item.get("message") or "")[:500],
                    "source": str(item.get("source") or ""),
                    "rule": str(item.get("rule") or ""),
                }
            )
        elif hasattr(item, "to_dict"):
            try:
                d = item.to_dict()
                if isinstance(d, dict):
                    out.append(d)
            except Exception:
                continue
    return out


def convert_incoming_verify(incoming: Any, *, source: str) -> DevVerifyView:
    if incoming is None:
        return DevVerifyView(
            metadata={"source": source, "acl_shape": "none", "acl_empty": True},
        )
    if isinstance(incoming, DevVerifyView):
        return incoming
    from butler.dev_engine.dev_state import VerifyResult

    if isinstance(incoming, VerifyResult):
        return DevVerifyView(
            status=incoming.status.value,
            diagnostics=[d.to_dict() for d in incoming.diagnostics[:20]],
            output_tail=str(incoming.output_tail or "")[:500],
            command=str(incoming.command or ""),
            exit_code=incoming.exit_code,
            elapsed_seconds=float(incoming.elapsed_seconds or 0.0),
            metadata={"source": source, "acl_shape": "verify_result"},
        )
    if isinstance(incoming, dict):
        return DevVerifyView(
            status=_normalize_status(incoming.get("status")),
            diagnostics=_diagnostics_from_any(incoming.get("diagnostics")),
            output_tail=str(incoming.get("output_tail") or incoming.get("output") or "")[:500],
            command=str(incoming.get("command") or ""),
            exit_code=incoming.get("exit_code"),
            elapsed_seconds=float(incoming.get("elapsed_seconds") or 0.0),
            metadata={"source": source, "acl_shape": "dict"},
        )
    return DevVerifyView(
        status="UNKNOWN",
        output_tail=str(incoming)[:500],
        metadata={"source": source, "acl_shape": "fallback_str", "acl_warn": "unknown_shape"},
    )


def to_dev_verify_view_loud(
    incoming: Any,
    *,
    source: str = "unknown",
) -> DevVerifyView:
    """Convert external verify payload; never raises."""
    try:
        return convert_incoming_verify(incoming, source=source)
    except Exception as exc:
        logger.debug("dev ACL adapt failed (%s): %s", source, exc)
        record_best_effort_skip(f"dev_acl.{source}", exc)
        from butler.core.metrics_sink import inc

        inc("dev_acl_degraded", labels={"source": str(source)[:48]})
        return DevVerifyView(
            status="UNKNOWN",
            metadata={
                "source": source,
                "acl_degraded": True,
                "acl_error": str(exc)[:160],
            },
        )
