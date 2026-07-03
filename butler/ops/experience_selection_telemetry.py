"""Log coding experience retrieval hits during dev delegate (phase C telemetry)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def selections_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit" / "experience_selections.jsonl"


def lifecycle_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit" / "experience_lifecycle.jsonl"


def record_experience_selection(
    *,
    session_key: str = "",
    task_preview: str = "",
    experience_id: str = "",
    experience_mode: str = "",
    keywords: list[str] | None = None,
    role: str = "dev",
    inferred_task_id: str = "",
    task_affinity: bool | None = None,
    selection_phase: str = "delegate_start",
) -> None:
    if not experience_id:
        return
    if task_affinity is None and inferred_task_id:
        from butler.ops.experience_selection_telemetry_ops import (
            experience_task_affinity_safe,
        )

        task_affinity = experience_task_affinity_safe(
            experience_id,
            inferred_task_id=inferred_task_id,
        )
    path = selections_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": time.time(),
        "session_key": session_key,
        "role": role,
        "task_preview": (task_preview or "")[:300],
        "experience_id": experience_id,
        "experience_mode": experience_mode,
        "keywords": (keywords or [])[:24],
        "inferred_task_id": (inferred_task_id or "")[:80],
        "task_affinity": task_affinity,
        "selection_phase": (selection_phase or "delegate_start")[:32],
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _resolve_row_task_affinity(row: dict[str, Any]) -> bool | None:
    """Use stored affinity or infer from task_preview + experience_id."""
    from butler.ops.experience_selection_telemetry_ops import (
        experience_task_affinity_safe,
        infer_b9_task_id_safe,
    )

    affinity = row.get("task_affinity")
    if affinity is True or affinity is False:
        return bool(affinity)
    eid = str(row.get("experience_id") or "").strip()
    if not eid:
        return None
    tid = str(row.get("inferred_task_id") or "").strip()
    if not tid:
        preview = str(row.get("task_preview") or "")
        tid = infer_b9_task_id_safe(preview)
    if not tid:
        return None
    return experience_task_affinity_safe(eid, inferred_task_id=tid)


def backfill_selection_task_affinity(*, dry_run: bool = True) -> dict[str, Any]:
    """Persist inferred task_affinity on historical selection rows."""
    path = selections_path()
    if not path.is_file():
        return {"updated": 0, "total": 0, "dry_run": dry_run}
    rows: list[dict[str, Any]] = []
    updated = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("task_affinity") is None and row.get("experience_id"):
            inferred = _resolve_row_task_affinity(row)
            if inferred is not None:
                row["task_affinity"] = inferred
                if not row.get("inferred_task_id"):
                    preview = str(row.get("task_preview") or "")
                    from butler.ops.experience_selection_telemetry_ops import (
                        infer_b9_task_id_safe,
                    )

                    tid = infer_b9_task_id_safe(preview)
                    if tid:
                        row["inferred_task_id"] = tid
                updated += 1
        rows.append(row)
    if not dry_run and updated:
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8",
        )
    return {"updated": updated, "total": len(rows), "dry_run": dry_run, "path": str(path)}


def summarize_experience_selections(*, limit: int = 200) -> dict[str, Any]:
    path = selections_path()
    if not path.is_file():
        return {"total": 0, "by_experience": {}, "path": str(path)}
    from collections import Counter

    by_exp: Counter[str] = Counter()
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        eid = str(row.get("experience_id") or "")
        if eid:
            by_exp[eid] += 1
    return {
        "total": total,
        "by_experience": dict(by_exp.most_common(12)),
        "path": str(path),
    }


def summarize_selection_precision(*, limit: int = 200) -> dict[str, Any]:
    """Share of experience hits that align with inferred B9 task id."""
    path = selections_path()
    if not path.is_file():
        return {"scored": 0, "aligned": 0, "misaligned": 0, "unknown": 0, "precision": None}
    scored = aligned = misaligned = unknown = 0
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not row.get("experience_id"):
            continue
        affinity = _resolve_row_task_affinity(row)
        if affinity is True:
            scored += 1
            aligned += 1
        elif affinity is False:
            scored += 1
            misaligned += 1
        else:
            unknown += 1
    precision = round(aligned / scored, 3) if scored else None
    return {
        "scored": scored,
        "aligned": aligned,
        "misaligned": misaligned,
        "unknown": unknown,
        "precision": precision,
        "path": str(path),
    }


def replay_selection_precision(*, limit: int = 200) -> dict[str, Any]:
    """Re-score historical rows with current retrieval eligibility + affinity."""
    path = selections_path()
    if not path.is_file():
        return {"replayed": 0, "precision": None}
    from butler.dev_engine.prod_delegate_bridge import infer_b9_task_id

    replayed = aligned = misaligned = 0
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        eid = str(row.get("experience_id") or "")
        if not eid:
            continue
        preview = str(row.get("task_preview") or "")
        inferred = str(row.get("inferred_task_id") or "") or infer_b9_task_id(preview)
        aff = _resolve_row_task_affinity({**row, "inferred_task_id": inferred})
        replayed += 1
        if aff is True:
            aligned += 1
        elif aff is False:
            misaligned += 1
    precision = round(aligned / replayed, 3) if replayed else None
    return {
        "replayed": replayed,
        "aligned": aligned,
        "misaligned": misaligned,
        "precision": precision,
        "path": str(path),
    }


def forward_selection_precision(*, limit: int = 200) -> dict[str, Any]:
    """Replay process_task on historical previews — measures new retrieval rules."""
    path = selections_path()
    if not path.is_file():
        return {"replayed": 0, "precision": None}
    from butler.config import get_butler_home
    from butler.dev_engine.coding_knowledge import ExperienceLibrary, TheoremLibrary, process_task
    from butler.dev_engine.prod_delegate_bridge import (
        experience_task_affinity,
        infer_b9_task_id,
        production_delegate_keywords,
    )
    from butler.memory.memory_scope import (
        delegate_project_id,
        load_delegate_experience_library,
        stack_tags_for_project,
    )

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not rows:
        return {"replayed": 0, "precision": None, "path": str(path)}

    tlib = TheoremLibrary()
    xlib = load_delegate_experience_library(
        butler_home=get_butler_home(),
        project="灵文1号",
        theorem_lib=tlib,
    )
    aligned = none = 0
    for row in rows:
        preview = str(row.get("task_preview") or "")
        if not preview.strip():
            continue
        inferred = infer_b9_task_id(preview)
        kws = production_delegate_keywords(preview)
        ctx = process_task(
            kws,
            tlib,
            xlib,
            strict_experience=True,
            project_id=delegate_project_id("灵文1号"),
            stack_tags=stack_tags_for_project("灵文1号"),
            inferred_task_id=inferred,
        )
        sel = ctx.selected_experience
        if sel is None:
            none += 1
            continue
        if experience_task_affinity(sel.id, inferred_task_id=inferred):
            aligned += 1
    scored = len(rows) - none
    precision = round(aligned / scored, 3) if scored else None
    return {
        "replayed": len(rows),
        "scored": scored,
        "aligned": aligned,
        "none": none,
        "precision": precision,
        "path": str(path),
    }


def record_experience_lifecycle(
    *,
    experience_id: str,
    action: str,
    success: bool,
    session_key: str = "",
    task_preview: str = "",
    role: str = "dev",
) -> None:
    if not experience_id or action in ("none", ""):
        return
    path = lifecycle_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": time.time(),
        "session_key": session_key,
        "role": role,
        "task_preview": (task_preview or "")[:300],
        "experience_id": experience_id,
        "action": action,
        "verify_passed": success,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize_experience_lifecycle(*, limit: int = 200) -> dict[str, Any]:
    path = lifecycle_path()
    if not path.is_file():
        return {"total": 0, "by_action": {}, "by_experience": {}, "path": str(path)}
    from collections import Counter

    by_action: Counter[str] = Counter()
    by_exp: Counter[str] = Counter()
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        act = str(row.get("action") or "")
        if act:
            by_action[act] += 1
        eid = str(row.get("experience_id") or "")
        if eid:
            by_exp[eid] += 1
    return {
        "total": total,
        "by_action": dict(by_action.most_common(8)),
        "by_experience": dict(by_exp.most_common(12)),
        "path": str(path),
    }


def apply_selected_experience_lifecycle(
    *,
    experience_id: str,
    success: bool,
    renew_days: float = 30.0,
    demote_days: float = 14.0,
    session_key: str = "",
    task_preview: str = "",
    role: str = "dev",
) -> dict[str, Any]:
    """Renew or demote the experience that guided this delegate run."""
    if not experience_id or not experience_id.strip():
        return {"action": "none"}
    import os

    from butler.config import get_butler_home
    from butler.dev_engine.coding_knowledge import ExperienceLibrary, TheoremLibrary

    path = os.path.join(get_butler_home(), "coding_experiences.json")
    tlib = TheoremLibrary()
    xlib = ExperienceLibrary.load_from_file(path, theorem_lib=tlib)
    exp = xlib.get(experience_id)
    if exp is None:
        return {"action": "missing", "experience_id": experience_id}
    if success:
        ok = xlib.renew(experience_id, extend_days=renew_days)
        action = "renewed" if ok else "renew_failed"
    else:
        ok = xlib.demote(experience_id, shrink_days=demote_days)
        action = "demoted" if ok else "demote_failed"
    if ok:
        xlib.save_to_file(path)
    result = {"action": action, "experience_id": experience_id, "success": success}
    from butler.ops.experience_selection_telemetry_ops import record_experience_lifecycle_safe

    record_experience_lifecycle_safe(
        experience_id=experience_id,
        action=action,
        success=success,
        session_key=session_key,
        task_preview=task_preview,
        role=role,
    )
    return result


__all__ = [
    "apply_selected_experience_lifecycle",
    "backfill_selection_task_affinity",
    "lifecycle_path",
    "record_experience_lifecycle",
    "record_experience_selection",
    "selections_path",
    "summarize_experience_lifecycle",
    "summarize_experience_selections",
    "summarize_selection_precision",
    "replay_selection_precision",
    "forward_selection_precision",
]
