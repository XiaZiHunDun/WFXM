"""Dev delegate result finalization (ENG-2)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.tools.delegate_phases import DelegateRunState

logger = logging.getLogger(__name__)


def peek_dev_engine_summary(session_key: str, role: str) -> dict[str, Any] | None:
    """Read DevState summary without popping (for background delegate jobs)."""
    norm = str(role or "").replace("_agent", "").strip().lower()
    if norm != "dev":
        return None
    try:
        from butler.dev_engine.dev_tools import _active_states, dev_engine_enabled

        if not dev_engine_enabled():
            return None
        ds = _active_states.get(session_key or "_default")
        if ds is None:
            return None
        summary = {
            "phase": ds.phase.value,
            "iterations": ds.iteration,
            "edits": len(ds.edit_history),
            "fixes": ds.fix_count,
            "verify_passed": ds.verify_result.passed,
        }
        tail = getattr(ds.verify_result, "output_tail", "") or ""
        if tail.strip():
            summary["verify_output_tail"] = tail.strip()[-800:]
        if ds.coding_knowledge.mode:
            summary["coding_knowledge"] = ds.coding_knowledge.to_dict()
        return summary
    except Exception as exc:  # noqa: BLE001 — best-effort read
        logger.debug("peek dev engine summary skipped: %s", exc)
        return None


def attach_dev_engine_summary(state: DelegateRunState, payload: dict[str, Any]) -> None:
    """Attach DevState summary to delegate result when engine active (6g, DA6)."""
    norm = state.role.replace("_agent", "").strip().lower()
    if norm != "dev":
        return
    try:
        from butler.dev_engine.dev_tools import _active_states, dev_engine_enabled

        if not dev_engine_enabled():
            return
        sk = state.child_session_key or state.session_key or "_default"
        ds = _active_states.pop(sk, None)
        if ds is None:
            return
        payload["dev_engine"] = {
            "phase": ds.phase.value,
            "iterations": ds.iteration,
            "edits": len(ds.edit_history),
            "fixes": ds.fix_count,
            "verify_passed": ds.verify_result.passed,
        }
        if ds.coding_knowledge.mode:
            payload["dev_engine"]["coding_knowledge"] = ds.coding_knowledge.to_dict()

        exp_id = ds.coding_knowledge.experience_id or ""
        if exp_id:
            try:
                from butler.ops.experience_selection_telemetry import (
                    apply_selected_experience_lifecycle,
                )

                lifecycle = apply_selected_experience_lifecycle(
                    experience_id=exp_id,
                    success=bool(ds.verify_result.passed),
                    session_key=state.child_session_key or state.session_key or "",
                    task_preview=state.task or "",
                    role=state.role,
                )
                payload["dev_engine"]["experience_lifecycle"] = lifecycle
            except Exception:
                pass

        try_extract_experience(ds, state)
        _record_dev_delegate_outcome(ds, state)
    except Exception as exc:  # noqa: BLE001 — best-effort summary
        logger.debug("DevState summary attachment skipped: %s", exc)


def _record_dev_delegate_outcome(ds: Any, state: DelegateRunState) -> None:
    try:
        from butler.memory.memory_scope import delegate_project_id
        from butler.ops.prod_experience_effectiveness import record_dev_delegate_outcome

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
        try:
            from butler.ops.g1_04_prod_evidence import record_g1_04_production_evidence

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
        except Exception:
            pass
    except Exception:
        pass


def try_extract_experience(ds: Any, state: DelegateRunState) -> None:
    """Best-effort: extract and persist a coding experience on task success."""
    try:
        from butler.dev_engine.dev_state import DevPhase

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

        from butler.config import get_butler_home
        from butler.dev_engine.coding_knowledge import (
            ExperienceLibrary,
            TheoremLibrary,
            extract_experience_candidate,
        )
        from butler.memory.memory_scope import (
            coding_experiences_save_path,
            scope_for_extracted_experience,
        )

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
    except Exception as exc:
        logger.debug("Experience extraction skipped: %s", exc)


__all__ = [
    "attach_dev_engine_summary",
    "peek_dev_engine_summary",
    "try_extract_experience",
]
