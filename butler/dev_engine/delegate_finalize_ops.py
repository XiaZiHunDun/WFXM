"""Delegate finalize best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from butler.core.best_effort import safe_best_effort
from butler.config import get_butler_home
from butler.core.dev_state_context_adapter import (
    loop_dev_state_view_to_payload,
    to_loop_dev_state_view,
)
from butler.dev_engine.coding_knowledge import (
    ExperienceLibrary,
    TheoremLibrary,
    extract_experience_candidate,
)
from butler.dev_engine.dev_state import DevPhase
from butler.dev_engine.dev_tools import _active_states, dev_engine_enabled
from butler.dev_engine.review_closure import nexus_sprint_review_handoff
from butler.memory.memory_scope import (
    coding_experiences_save_path,
    delegate_project_id,
    scope_for_extracted_experience,
)
from butler.ops.experience_selection_telemetry import apply_selected_experience_lifecycle
from butler.ops.g1_04_prod_evidence import record_g1_04_production_evidence
from butler.ops.prod_experience_effectiveness import record_dev_delegate_outcome

if TYPE_CHECKING:
    from butler.tools.delegate_phases import DelegateRunState

logger = logging.getLogger(__name__)


def peek_dev_engine_summary_safe(session_key: str, role: str) -> dict[str, Any] | None:
    norm = str(role or "").replace("_agent", "").strip().lower()
    if norm != "dev":
        return None

    def _run() -> dict[str, Any] | None:
        if not dev_engine_enabled():
            return None
        ds = _active_states.get(session_key or "_default")
        if ds is None:
            return None
        view = to_loop_dev_state_view(ds, source="peek")
        summary = loop_dev_state_view_to_payload(view)
        tail = getattr(ds.verify_result, "output_tail", "") or ""
        if tail.strip():
            summary["verify_output_tail"] = tail.strip()[-800:]
        if ds.coding_knowledge.mode:
            summary["coding_knowledge"] = ds.coding_knowledge.to_dict()
        if ds.review_summary.findings_count or not ds.review_summary.passed:
            summary["review"] = ds.review_summary.to_dict()
        return cast(dict[str, Any] | None, summary)

    return cast(dict[str, Any] | None, safe_best_effort(_run, label="delegate_finalize.peek_summary", default=None))


def attach_review_handoff_safe(state: DelegateRunState, payload: dict[str, Any]) -> None:
    def _run() -> None:
        handoff = nexus_sprint_review_handoff(state.category)
        if handoff:
            payload["review_handoff"] = handoff.strip()

    safe_best_effort(_run, label="delegate_finalize.review_handoff", default=None)


def apply_experience_lifecycle_safe(
    ds: Any,
    state: DelegateRunState,
) -> dict[str, Any] | None:
    exp_id = ds.coding_knowledge.experience_id or ""
    if not exp_id:
        return None

    def _run() -> dict[str, Any]:
        return cast(
            dict[str, Any],
            apply_selected_experience_lifecycle(
                experience_id=exp_id,
                success=bool(ds.verify_result.passed),
                session_key=state.child_session_key or state.session_key or "",
                task_preview=state.task or "",
                role=state.role,
            ),
        )

    return cast(dict[str, Any] | None, safe_best_effort(_run, label="delegate_finalize.experience_lifecycle", default=None))


def attach_dev_engine_payload_safe(
    state: DelegateRunState,
    payload: dict[str, Any],
) -> Any | None:
    """Pop DevState, fill payload; return ds for follow-up hooks."""

    def _run() -> Any | None:
        if not dev_engine_enabled():
            return None
        sk = state.child_session_key or state.session_key or "_default"
        ds = _active_states.pop(sk, None)
        if ds is None:
            return None
        view = to_loop_dev_state_view(ds, source="attach")
        payload["dev_engine"] = loop_dev_state_view_to_payload(view)
        if ds.coding_knowledge.mode:
            payload["dev_engine"]["coding_knowledge"] = ds.coding_knowledge.to_dict()
        if ds.review_summary.findings_count or not ds.review_summary.passed:
            payload["dev_engine"]["review"] = ds.review_summary.to_dict()
        return ds

    return safe_best_effort(_run, label="delegate_finalize.attach_summary", default=None)


def record_dev_delegate_outcome_safe(ds: Any, state: DelegateRunState) -> None:
    def _run() -> None:
        record_dev_delegate_outcome(
            session_key=state.child_session_key or state.session_key or "",
            role=state.role,
            project=delegate_project_id(state.project),
            task_id=state.task_id,
            task_preview=state.task or "",
            category=state.category,
            category_meta=state.category_meta,
            success=bool(ds.verify_result.passed),
            verify_passed=bool(ds.verify_result.passed),
            experience_id=ds.coding_knowledge.experience_id,
            experience_mode=ds.coding_knowledge.mode,
            reactivation_count=int(
                getattr(ds, "_coding_knowledge_reactivation_count", 0) or 0
            ),
        )
        record_g1_04_evidence_safe(ds, state)

    safe_best_effort(_run, label="delegate_finalize.record_outcome", default=None)


def record_g1_04_evidence_safe(ds: Any, state: DelegateRunState) -> None:
    def _run() -> None:
        record_g1_04_production_evidence(
            role=state.role,
            project=delegate_project_id(state.project),
            success=bool(ds.verify_result.passed),
            verify_passed=bool(ds.verify_result.passed),
            task_id=state.task_id,
            task_preview=state.task or "",
            capture_source="delegate_pipeline",
            category=state.category,
            category_meta=state.category_meta,
        )

    safe_best_effort(_run, label="delegate_finalize.g1_04_evidence", default=None)


def try_extract_experience_safe(ds: Any, state: DelegateRunState) -> None:
    def _run() -> None:
        if ds.phase != DevPhase.DONE or not ds.verify_result.passed:
            return
        activated = getattr(ds, "_coding_knowledge_theorems", None)
        if not activated:
            return
        snippets = [
            e.new_content for e in ds.edit_history if e.new_content and len(e.new_content) > 20
        ]
        if not snippets:
            return
        candidate = extract_experience_candidate(ds.task_description, snippets, activated)
        if candidate is None:
            return
        butler_home = get_butler_home()
        save_path = coding_experiences_save_path(
            butler_home=butler_home,
            project=state.project,
        )
        candidate.scope = scope_for_extracted_experience(state.project)
        tlib = TheoremLibrary()
        xlib = ExperienceLibrary.load_from_file(str(save_path), theorem_lib=tlib)
        ok, _ = xlib.add(candidate)
        if ok:
            xlib.save_to_file(str(save_path))
            logger.debug("Extracted coding experience %s → %s", candidate.id, save_path)

    safe_best_effort(_run, label="delegate_finalize.extract_experience", default=None)
