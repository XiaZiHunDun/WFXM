"""Production delegate failures → L3 project coding experiences + b9_lessons."""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any

from butler.memory.memory_scope import MemoryScope


def classify_production_failure(
    *,
    failure_reason: str,
    issues: list[str] | None = None,
    dev_engine: dict[str, Any] | None = None,
) -> str:
    """Coarse bucket aligned with prod_delegate_snapshots rates."""
    text = " ".join(issues or []).lower()
    reason = (failure_reason or "").strip().lower()
    if "read_state" in text or ("read_file" in text and "before" in text):
        return "read_state"
    if "tool_error" in text or "metacharacter" in text or "not allowed" in text:
        return "tool_wrong"
    if reason in ("verify_failed", "verify_fail"):
        return "verify_fail"
    if dev_engine and dev_engine.get("verify_passed") is False:
        return "verify_fail"
    if "patch" in text and "wrong" in text:
        return "patch_wrong"
    if "pytest" in text or "no test" in text:
        return "no_test"
    return "other_fail"


def should_upsert_production_failure_experience(
    *,
    role: str,
    success: bool,
    project: str,
    capture_source: str,
    task_preview: str = "",
    task_id: str = "",
    dev_engine: dict[str, Any] | None = None,
) -> bool:
    """True for real production dev failures (not B9/SWE/drill noise)."""
    from butler.ops.b9_prod_weekly import is_production_audit_noise

    norm = str(role or "").replace("_agent", "").strip().lower()
    if norm != "dev":
        return False
    if not str(project or "").strip():
        return False
    verify_failed = bool(dev_engine and dev_engine.get("verify_passed") is False)
    if success and not verify_failed:
        return False
    rec = {
        "role": role,
        "capture_source": capture_source,
        "task_preview": task_preview,
        "task_id": task_id,
    }
    if is_production_audit_noise(rec):
        return False
    preview = task_preview.lower()
    if "[category:b9-benchmark]" in preview or "[category:swe-benchmark]" in preview:
        return False
    if "[category:lingwen-prod-sample]" in preview or "[category:lingwen-drill]" in preview:
        return False
    if task_id.startswith("B9L_") or task_id.startswith("SWE-"):
        return False
    return capture_source == "delegate_pipeline" or not capture_source


def _prod_fail_experience_id(*, project: str, task_id: str, task: str) -> str:
    key = f"{project}:{task_id or task[:160]}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return f"PROD_FAIL_{digest}"


def _resolve_project_workspace(project_name: str) -> Path | None:
    try:
        from butler.project.manager import get_project_manager

        proj = get_project_manager().get_project(project_name)
        if proj is None or not getattr(proj, "workspace", None):
            return None
        return Path(proj.workspace).expanduser().resolve()
    except Exception:
        return None


def record_production_failure_lesson(
    *,
    project: str,
    task_id: str,
    task: str,
    failure_reason: str,
    classification: str,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    from butler.ops.b9_lessons import record_b9_lesson

    tail = ""
    if issues:
        tail = str(issues[-1])[:400]
    row = {
        "task_id": task_id or _prod_fail_experience_id(project=project, task_id="", task=task),
        "project": project,
        "kind": "production_failure",
        "classification": classification,
        "passed": False,
        "mode": "production",
        "failure_reason": failure_reason,
        "failure_tail": tail,
        "lesson": f"production delegate failure ({classification})",
        "pattern_summary": (task or "")[:240],
        "task_preview": (task or "")[:200],
    }
    record_b9_lesson(row)
    return row


def upsert_production_failure_experience(
    *,
    project: str,
    task: str,
    task_id: str = "",
    failure_reason: str = "",
    issues: list[str] | None = None,
    dev_engine: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write or refresh a private L3 coding experience from a production failure."""
    from butler.dev_engine.b9_experience_retrieval import (
        B9_EXPERIENCE_THEOREM_BASIS,
        FAILURE_CLASS_KEYWORDS,
    )
    from butler.dev_engine.coding_knowledge import CodingExperience, ExperienceLibrary, TheoremLibrary
    from butler.memory.memory_scope import project_coding_experiences_path

    ws = _resolve_project_workspace(project)
    if ws is None:
        return {"ok": False, "reason": "workspace_not_found", "project": project}

    classification = classify_production_failure(
        failure_reason=failure_reason,
        issues=issues,
        dev_engine=dev_engine,
    )
    exp_id = _prod_fail_experience_id(project=project, task_id=task_id, task=task)
    tail = ""
    if issues:
        tail = str(issues[-1])[:800]
    kws = list(FAILURE_CLASS_KEYWORDS.get(classification, ()))
    preview_tokens = re.findall(r"[a-z0-9_]{3,}", (task or "").lower())
    kws.extend(preview_tokens[:8])
    keywords = ",".join(dict.fromkeys(kws))

    pattern = (
        f"Production failure in {project} ({classification}).\n"
        f"task: {(task or '')[:400]}\n"
        f"reason: {failure_reason}\n"
        f"evidence: {tail}"
    )[:2000]

    scope = MemoryScope(
        level="project",
        project_id=project,
        visibility="private",
        source="prod_failure",
    )

    exp = CodingExperience(
        id=exp_id,
        title=f"Prod failure {project} ({classification})",
        domain=["prod", "failure", classification],
        theorem_basis=set(B9_EXPERIENCE_THEOREM_BASIS),
        context=f"{project}; {classification}; {failure_reason}",
        pattern=pattern,
        benchmarks={
            "failure_class": classification,
            "project": project,
            "retrieval_keywords": keywords,
        },
        validity_start=time.time(),
        validity_end=time.time() + 180 * 86400,
        scope=scope,
    )

    save_path = project_coding_experiences_path(ws)
    tlib = TheoremLibrary()
    xlib = ExperienceLibrary.load_from_file(str(save_path), theorem_lib=tlib)
    if xlib.get(exp_id) is not None:
        xlib.remove(exp_id)
    ok, detail = xlib.add(exp, skip_validation=True)
    lesson_row: dict[str, Any] | None = None
    if ok:
        xlib.save_to_file(str(save_path))
        lesson_row = record_production_failure_lesson(
            project=project,
            task_id=task_id or exp_id,
            task=task,
            failure_reason=failure_reason,
            classification=classification,
            issues=issues,
        )
    return {
        "ok": ok,
        "detail": detail,
        "experience_id": exp_id,
        "save_path": str(save_path),
        "classification": classification,
        "lesson": lesson_row,
    }


def follow_up_production_capture(
    *,
    role: str,
    task: str,
    success: bool,
    project: str,
    capture_source: str = "",
    task_id: str = "",
    task_preview: str = "",
    failure_reason: str = "",
    issues: list[str] | None = None,
    dev_engine: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """L3 experience + lesson when a production-shaped failure is captured."""
    preview = task_preview or task
    if not should_upsert_production_failure_experience(
        role=role,
        success=success,
        project=project,
        capture_source=capture_source,
        task_preview=preview,
        task_id=task_id,
        dev_engine=dev_engine,
    ):
        return {"action": "skipped", "reason": "not_production_failure"}
    return {
        "action": "upserted",
        **upsert_production_failure_experience(
            project=project,
            task=task,
            task_id=task_id,
            failure_reason=failure_reason,
            issues=issues,
            dev_engine=dev_engine,
        ),
    }


__all__ = [
    "classify_production_failure",
    "follow_up_production_capture",
    "record_production_failure_lesson",
    "should_upsert_production_failure_experience",
    "upsert_production_failure_experience",
]
