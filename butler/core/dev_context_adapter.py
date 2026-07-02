"""Anti-corruption adapter: external verify shapes → DevVerifyView → VerifyResult."""

from __future__ import annotations

from typing import Any

from butler.contracts.dev_context_ports import DevVerifyView


def to_dev_verify_view(
    incoming: Any,
    *,
    source: str = "unknown",
) -> DevVerifyView:
    """Convert external verify payload; never raises."""
    from butler.core.dev_context_adapter_ops import to_dev_verify_view_loud

    return to_dev_verify_view_loud(incoming, source=source)


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
    from butler.dev_engine.dev_state import VerifyResult

    if isinstance(incoming, VerifyResult):
        return incoming
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
