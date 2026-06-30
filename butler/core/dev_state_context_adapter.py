"""Anti-corruption adapter: external dev state shapes → LoopDevStateView."""

from __future__ import annotations

import logging
from typing import Any

from butler.contracts.dev_state_ports import LoopDevStateView, normalize_dev_phase
from butler.core.best_effort import record_best_effort_skip

logger = logging.getLogger(__name__)


def _bool_or_none(raw: Any) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in ("1", "true", "yes", "on", "pass", "passed"):
        return True
    if text in ("0", "false", "no", "off", "fail", "failed"):
        return False
    return None


def _review_passed_from_dict(data: dict[str, Any]) -> bool | None:
    review = data.get("review")
    if isinstance(review, dict) and "passed" in review:
        return _bool_or_none(review.get("passed"))
    if "review_passed" in data:
        return _bool_or_none(data.get("review_passed"))
    return None


def _verify_passed_from_dict(data: dict[str, Any]) -> bool | None:
    if "verify_passed" in data:
        return _bool_or_none(data.get("verify_passed"))
    verify = data.get("verify")
    if isinstance(verify, dict):
        status = str(verify.get("status") or "").upper()
        if status == "PASS":
            return True
        if status in ("FAIL", "TIMEOUT"):
            return False
    return None


def to_loop_dev_state_view(
    incoming: Any,
    *,
    source: str = "unknown",
) -> LoopDevStateView:
    """Convert external dev state payload; never raises."""
    try:
        if incoming is None:
            return LoopDevStateView(
                metadata={"source": source, "acl_shape": "none", "acl_empty": True},
            )
        if isinstance(incoming, LoopDevStateView):
            return incoming
        if hasattr(incoming, "phase") and hasattr(incoming, "edit_history"):
            from butler.dev_engine.dev_state import DevPhase, DevState

            if isinstance(incoming, DevState):
                phase = incoming.phase.value if isinstance(incoming.phase, DevPhase) else str(incoming.phase)
                verify_passed = None
                if incoming.verify_result is not None:
                    verify_passed = bool(incoming.verify_result.passed)
                review_passed = None
                if incoming.review_summary.findings_count or not incoming.review_summary.passed:
                    review_passed = incoming.review_summary.passed
                return LoopDevStateView(
                    phase=normalize_dev_phase(phase),
                    verify_passed=verify_passed,
                    review_passed=review_passed,
                    edits=len(incoming.edit_history),
                    fixes=int(incoming.fix_count),
                    iterations=int(incoming.iteration),
                    is_terminal=bool(incoming.is_terminal),
                    metadata={"source": source, "acl_shape": "dev_state"},
                )
        if isinstance(incoming, dict):
            phase = normalize_dev_phase(incoming.get("phase"))
            edits = int(incoming.get("edits") or incoming.get("edit_count") or 0)
            fixes = int(incoming.get("fixes") or incoming.get("fix_count") or 0)
            iterations = int(incoming.get("iterations") or incoming.get("iteration") or 0)
            is_terminal = phase in ("DONE", "STUCK") or _bool_or_none(incoming.get("is_terminal")) is True
            return LoopDevStateView(
                phase=phase,
                verify_passed=_verify_passed_from_dict(incoming),
                review_passed=_review_passed_from_dict(incoming),
                edits=edits,
                fixes=fixes,
                iterations=iterations,
                is_terminal=is_terminal,
                metadata={"source": source, "acl_shape": "dict"},
            )
        return LoopDevStateView(
            phase="PLAN",
            metadata={"source": source, "acl_shape": "fallback", "acl_warn": "unknown_shape"},
        )
    except Exception as exc:
        logger.debug("dev state ACL adapt failed (%s): %s", source, exc)
        record_best_effort_skip(f"dev_state_acl.{source}", exc)
        return LoopDevStateView(
            phase="PLAN",
            metadata={
                "source": source,
                "acl_degraded": True,
                "acl_error": str(exc)[:160],
            },
        )


def loop_dev_state_view_to_payload(view: LoopDevStateView) -> dict[str, Any]:
    """Normalize outbound delegate dev_engine dict."""
    out: dict[str, Any] = {
        "phase": view.phase,
        "iterations": view.iterations,
        "edits": view.edits,
        "fixes": view.fixes,
        "dev_state_view_version": view.schema_version,
    }
    if view.verify_passed is not None:
        out["verify_passed"] = view.verify_passed
    if view.review_passed is not None:
        out["review_passed"] = view.review_passed
    if view.is_terminal:
        out["is_terminal"] = True
    shape = view.metadata.get("acl_shape")
    if shape:
        out["dev_state_acl_shape"] = shape
    return out


def apply_dev_state_view_to_diagnostics(
    view: LoopDevStateView,
    diagnostics: dict[str, Any] | None,
) -> None:
    if not isinstance(diagnostics, dict):
        return
    diagnostics["dev_state_view_version"] = view.schema_version
    diagnostics["dev_state_phase"] = view.phase
    if view.verify_passed is not None:
        diagnostics["dev_state_verify_passed"] = view.verify_passed
    if view.review_passed is not None:
        diagnostics["dev_state_review_passed"] = view.review_passed
    if view.metadata.get("acl_degraded"):
        diagnostics["dev_state_acl_degraded"] = True


def dev_engine_dict_to_view(dev_engine: dict[str, Any] | None, *, source: str = "delegate") -> LoopDevStateView:
    if not isinstance(dev_engine, dict):
        return to_loop_dev_state_view(None, source=source)
    return to_loop_dev_state_view(dev_engine, source=source)
