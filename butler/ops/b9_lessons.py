"""B9 learning loop — lessons from oracle gold and LIVE runs."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, cast

from butler.dev_engine.b9_oracle_curriculum import (
    B9_ORACLE_EPISODES,
    B9CurriculumEpisode,
    episode_for_spec,
    export_curriculum_to_disk,
    get_episode,
)
from butler.dev_engine.b9_types import B9Result, B9TaskSpec
from butler.ops.b9_failure_analysis import classify_b9_failure

_LESSONS_NAME = "b9_lessons.jsonl"


def b9_lessons_path() -> Path:
    from butler.config import get_butler_home

    return cast(Path, get_butler_home()) / "audit" / _LESSONS_NAME


def record_b9_lesson(record: dict[str, Any]) -> Path:
    path = b9_lessons_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {**record, "ts": record.get("ts", time.time())}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def load_lessons_for_task(task_id: str, *, limit: int = 3) -> list[dict[str, Any]]:
    path = b9_lessons_path()
    if not path.is_file() or limit <= 0:
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("task_id") or "") == task_id:
            rows.append(row)
    return rows[-limit:]


def format_b9_lessons_block(task_id: str, *, limit: int = 2) -> str:
    lessons = load_lessons_for_task(task_id, limit=limit)
    if not lessons:
        return ""
    lines = ["<b9-lessons>", f"## Prior runs for {task_id}"]
    for row in lessons:
        kind = row.get("kind", "?")
        cls = row.get("classification", "")
        passed = row.get("passed")
        summary = str(row.get("pattern_summary") or row.get("lesson") or "")[:240]
        lines.append(f"- [{kind}/{cls}] passed={passed}: {summary}")
    lines.append("</b9-lessons>")
    return "\n".join(lines)


def _lesson_from_episode(ep: B9CurriculumEpisode, *, kind: str = "oracle_gold") -> dict[str, Any]:
    return {
        "task_id": ep.task_id,
        "kind": kind,
        "classification": "passed",
        "passed": True,
        "skill_name": ep.skill_name,
        "pattern_summary": ep.pattern_summary,
        "steps": [s.to_dict() for s in ep.steps],
        "tags": list(ep.tags),
    }


def record_oracle_gold_lesson(task_id: str) -> dict[str, Any] | None:
    ep = get_episode(task_id)
    if ep is None:
        return None
    row = _lesson_from_episode(ep)
    record_b9_lesson(row)
    return row


def record_b9_run_lesson(
    result: B9Result,
    spec: B9TaskSpec,
    *,
    project: str = "",
) -> dict[str, Any]:
    """Record a lesson from a B9 task run (oracle or LIVE)."""
    classification = classify_b9_failure(
        task_id=result.task_id,
        passed=result.passed,
        tools_used=result.tools_used,
        failure_reasons=result.failure_reasons,
    )
    ep = episode_for_spec(spec)
    if result.passed and ep is not None:
        row = _lesson_from_episode(ep, kind="live_success" if result.mode == "live" else "oracle_gold")
        if project:
            row["project"] = project
    else:
        tail = ""
        if result.failure_reasons:
            tail = str(result.failure_reasons[-1])[:400]
        lesson = f"classification={classification}"
        if ep is not None:
            lesson = f"{ep.pattern_summary} | failed: {classification}"
        pattern_summary = ep.pattern_summary if ep else ""
        if not pattern_summary and result.task_id.startswith("SWE-"):
            from butler.dev_engine.swe_curriculum import get_swe_playbook

            swe_pb = get_swe_playbook(result.task_id)
            if swe_pb is not None:
                pattern_summary = swe_pb.pattern_summary
        row = {
            "task_id": result.task_id,
            "project": project,
            "kind": "live_failure" if result.mode == "live" else "oracle_miss",
            "classification": classification,
            "passed": result.passed,
            "mode": result.mode,
            "tools_used": list(result.tools_used),
            "failure_tail": tail,
            "lesson": lesson,
            "pattern_summary": pattern_summary,
            "anti_patterns": list(ep.anti_patterns) if ep else [],
        }
    record_b9_lesson(row)
    from butler.ops.b9_lessons_ops import follow_up_lesson_experience_safe

    row["experience_followup"] = follow_up_lesson_experience_safe(row, result, spec)
    return row


def _experience_library_paths() -> tuple[str, Any]:
    import os

    from butler.config import get_butler_home
    from butler.dev_engine.coding_knowledge import ExperienceLibrary, TheoremLibrary

    xlib_path = os.path.join(get_butler_home(), "coding_experiences.json")
    tlib = TheoremLibrary()
    xlib = ExperienceLibrary.load_from_file(xlib_path, theorem_lib=tlib)
    return xlib_path, xlib


def renew_or_promote_live_success(ep: B9CurriculumEpisode) -> tuple[str, str]:
    """Extend B9_EX_* on LIVE pass, or seed from oracle episode if missing."""
    exp_id = f"B9_EX_{ep.task_id.replace('B9L_', '')}"
    xlib_path, xlib = _experience_library_paths()
    if xlib.get(exp_id) is not None:
        if xlib.renew(exp_id, extend_days=90):
            xlib.save_to_file(xlib_path)
            return "renewed", exp_id
        return "renew_failed", exp_id
    ok, detail = promote_episode_to_experience(ep, skip_if_exists=False)
    return ("promoted" if ok else "promote_failed"), detail


def upsert_failure_experience(
    *,
    task_id: str,
    classification: str,
    failure_tail: str,
    pattern_summary: str,
    anti_patterns: list[str] | None = None,
) -> tuple[bool, str]:
    """Record LIVE failure anti-pattern as B9_FAIL_* experience."""
    from butler.dev_engine.coding_knowledge import CodingExperience

    slug = task_id.replace("B9L_", "").replace("SWE-", "swe_")
    exp_id = f"B9_FAIL_{slug}"
    anti = "; ".join(anti_patterns or []) or "see failure_tail"
    pattern = (
        f"Task {task_id} failed with classification={classification}.\n"
        f"pattern: {pattern_summary}\n"
        f"avoid: {anti}\n"
        f"evidence: {(failure_tail or '')[:800]}"
    )
    xlib_path, xlib = _experience_library_paths()
    from butler.dev_engine.b9_experience_retrieval import (
        B9_EXPERIENCE_THEOREM_BASIS,
        apply_retrieval_benchmarks,
        enrich_b9_experience_context,
    )

    exp = CodingExperience(
        id=exp_id,
        title=f"B9 failure {task_id} ({classification})",
        domain=["b9", "failure", classification],
        theorem_basis=set(B9_EXPERIENCE_THEOREM_BASIS),
        context=enrich_b9_experience_context(task_id, classification=classification),
        pattern=pattern[:2000],
        benchmarks=apply_retrieval_benchmarks(
            {"b9_task": task_id, "failure_class": classification},
            task_id,
            classification=classification,
        ),
        validity_start=time.time(),
        validity_end=time.time() + 180 * 86400,
    )
    ok, detail = xlib.add(exp, skip_validation=True)
    if ok:
        xlib.save_to_file(xlib_path)
    return ok, detail


def follow_up_lesson_experience(
    row: dict[str, Any],
    result: B9Result,
    spec: B9TaskSpec,
) -> dict[str, Any]:
    """A2: lesson → coding_experiences.json (renew gold / upsert failure)."""
    ep = episode_for_spec(spec)
    if result.passed and result.mode == "live" and ep is not None:
        action, detail = renew_or_promote_live_success(ep)
        return {"action": action, "detail": detail, "task_id": result.task_id}
    if (
        not result.passed
        and result.mode == "live"
        and row.get("kind") == "live_failure"
    ):
        ok, detail = upsert_failure_experience(
            task_id=result.task_id,
            classification=str(row.get("classification") or "other_fail"),
            failure_tail=str(row.get("failure_tail") or ""),
            pattern_summary=str(row.get("pattern_summary") or row.get("lesson") or ""),
            anti_patterns=list(row.get("anti_patterns") or []),
        )
        return {
            "action": "failure_upserted" if ok else "failure_upsert_failed",
            "detail": detail,
            "task_id": result.task_id,
        }
    return {"action": "none", "task_id": result.task_id}


def promote_episode_to_experience(ep: B9CurriculumEpisode, *, skip_if_exists: bool = True) -> tuple[bool, str]:
    """Promote oracle episode to ~/.butler/coding_experiences.json (B9_EX_*)."""
    from butler.dev_engine.coding_knowledge import CodingExperience

    exp_id = f"B9_EX_{ep.task_id.replace('B9L_', '')}"
    xlib_path, xlib = _experience_library_paths()
    if skip_if_exists and xlib.get(exp_id) is not None:
        return False, "exists"
    steps_text = "\n".join(f"{s.action} {s.target}: {s.detail}" for s in ep.steps)
    pattern = f"{ep.pattern_summary}\n\nsteps:\n{steps_text}"
    from butler.dev_engine.b9_experience_retrieval import (
        B9_EXPERIENCE_THEOREM_BASIS,
        apply_retrieval_benchmarks,
        enrich_b9_experience_context,
    )

    exp = CodingExperience(
        id=exp_id,
        title=f"B9 {ep.title}",
        domain=["b9", *list(ep.tags)],
        theorem_basis=set(B9_EXPERIENCE_THEOREM_BASIS),
        context=enrich_b9_experience_context(ep.task_id),
        pattern=pattern[:2000],
        benchmarks=apply_retrieval_benchmarks({"b9_task": ep.task_id}, ep.task_id),
        validity_start=time.time(),
        validity_end=time.time() + 365 * 86400,
    )
    ok, detail = xlib.add(exp, skip_validation=True)
    if ok:
        xlib.save_to_file(xlib_path)
    return ok, detail


def export_curriculum_and_seed_experiences(
    *,
    task_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Export curriculum JSON + seed CodingExperience for listed tasks (default Tier-1)."""
    from butler.dev_engine.b9_tiers import b9_task_tier

    curriculum_path = export_curriculum_to_disk()
    lessons_recorded = 0
    experiences_added = 0
    experiences_skipped = 0
    targets = task_ids or list(B9_ORACLE_EPISODES.keys())
    for tid in targets:
        ep = get_episode(tid)
        if ep is None:
            continue
        if record_oracle_gold_lesson(tid) is not None:
            lessons_recorded += 1
        ok, detail = promote_episode_to_experience(ep)
        if ok:
            experiences_added += 1
        elif detail == "exists":
            experiences_skipped += 1
    tier1_eps = [tid for tid in targets if b9_task_tier(tid) == 1]
    return {
        "curriculum_path": str(curriculum_path),
        "lessons_recorded": lessons_recorded,
        "experiences_added": experiences_added,
        "experiences_skipped": experiences_skipped,
        "tier1_episodes": tier1_eps,
        "episode_count": len(B9_ORACLE_EPISODES),
    }


__all__ = [
    "b9_lessons_path",
    "export_curriculum_and_seed_experiences",
    "follow_up_lesson_experience",
    "format_b9_lessons_block",
    "load_lessons_for_task",
    "promote_episode_to_experience",
    "record_b9_lesson",
    "record_b9_run_lesson",
    "record_oracle_gold_lesson",
    "renew_or_promote_live_success",
    "upsert_failure_experience",
]
