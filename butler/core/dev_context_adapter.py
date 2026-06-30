"""Anti-corruption adapter: external verify shapes → DevVerifyView → VerifyResult."""

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


def to_dev_verify_view(
    incoming: Any,
    *,
    source: str = "unknown",
) -> DevVerifyView:
    """Convert external verify payload; never raises."""
    try:
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
    except Exception as exc:
        logger.debug("dev ACL adapt failed (%s): %s", source, exc)
        record_best_effort_skip(f"dev_acl.{source}", exc)
        try:
            from butler.core.metrics_sink import inc

            inc("dev_acl_degraded", labels={"source": str(source)[:48]})
        except Exception:
            pass
        return DevVerifyView(
            status="UNKNOWN",
            metadata={
                "source": source,
                "acl_degraded": True,
                "acl_error": str(exc)[:160],
            },
        )


def dev_verify_view_to_result(view: DevVerifyView) -> Any:
    """Map ACL view to DevState VerifyResult."""
    from butler.dev_engine.dev_state import DiagSeverity, Diagnostic, VerifyResult, VerifyStatus

    try:
        status = VerifyStatus(view.status)
    except ValueError:
        status = VerifyStatus.UNKNOWN

    diags: list[Diagnostic] = []
    for d in view.diagnostics:
        sev_raw = str(d.get("severity") or "error").lower()
        try:
            severity = DiagSeverity(sev_raw)
        except ValueError:
            severity = DiagSeverity.ERROR
        diags.append(
            Diagnostic(
                file=str(d.get("file") or ""),
                line=int(d.get("line") or 0),
                column=int(d.get("column") or 0),
                severity=severity,
                message=str(d.get("message") or "")[:500],
                source=str(d.get("source") or ""),
                rule=str(d.get("rule") or ""),
            )
        )
    return VerifyResult(
        status=status,
        diagnostics=diags,
        command=view.command,
        elapsed_seconds=view.elapsed_seconds,
        exit_code=view.exit_code,
        output_tail=view.output_tail,
    )


def to_verify_result(incoming: Any, *, source: str = "unknown") -> Any:
    """Single entry: external verify → VerifyResult."""
    view = to_dev_verify_view(incoming, source=source)
    return dev_verify_view_to_result(view)


def apply_dev_verify_view_to_state(
    view: DevVerifyView,
    state: Any,
) -> None:
    """Record ACL observability on DevState (optional metadata bag)."""
    bag = getattr(state, "_acl_metadata", None)
    if not isinstance(bag, dict):
        bag = {}
        setattr(state, "_acl_metadata", bag)
    bag["dev_verify_view_version"] = view.schema_version
    shape = view.metadata.get("acl_shape")
    if shape:
        bag["dev_acl_shape"] = shape
    if view.metadata.get("acl_warn") or view.metadata.get("acl_degraded"):
        bag["dev_acl_degraded"] = True
