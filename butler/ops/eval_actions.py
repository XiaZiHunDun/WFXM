"""Hard feedback actions from eval scores (O6) with audit trail."""

from __future__ import annotations

from butler.env_parse import float_env
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from butler.ops.eval_feedback import FeedbackReport, FeedbackSuggestion, analyse_scores

logger = logging.getLogger(__name__)

_STATE_PATH_NAME = "eval_hard_feedback_state.json"


def hard_feedback_enabled() -> bool:
    return os.getenv("BUTLER_EVAL_HARD_FEEDBACK", "1").strip() in ("1", "true", "yes")


def _min_interval_seconds() -> float:
    try:
        hours = float_env("BUTLER_EVAL_HARD_FEEDBACK_HOURS", 1)
        if hours <= 0:
            return 0.0
        return max(0.25, hours) * 3600.0
    except ValueError:
        return 3600.0


def _audit_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit" / "eval_feedback.jsonl"


def _state_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "config" / _STATE_PATH_NAME


def _append_audit(record: dict[str, Any]) -> None:
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record.setdefault("ts", time.time())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _should_run() -> bool:
    path = _state_path()
    if not path.is_file():
        return True
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        last = float(state.get("last_run", 0.0) or 0.0)
        return (time.time() - last) >= _min_interval_seconds()
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return True


def _mark_run(summary: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"last_run": time.time(), "summary": summary}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _apply_memory_action(suggestion: FeedbackSuggestion) -> dict[str, Any]:
    from butler.memory.retrieval_ranking import memory_half_life_days
    from butler.ops.eval_config_overrides import adjust_memory_half_life

    base = memory_half_life_days()
    direction = "up" if suggestion.metric_value < suggestion.threshold else "down"
    if suggestion.metric_name in ("memory_effectiveness", "memory_benchmark.pass_rate"):
        direction = "up"
    new_val = adjust_memory_half_life(direction=direction, base=base)
    action = {
        "action": "adjust_memory_half_life",
        "direction": direction,
        "new_value": new_val,
        "metric": suggestion.metric_name,
        "metric_value": suggestion.metric_value,
    }
    _append_audit(action)
    return action


def _apply_experience_lifecycle(report: FeedbackReport) -> dict[str, Any]:
    """Demote experiences when dev/memory benchmarks are critically low."""
    try:
        from butler.dev_engine.coding_knowledge import ExperienceLibrary, TheoremLibrary
        from butler.config import get_butler_home

        path = get_butler_home() / "coding_experiences.json"
        tlib = TheoremLibrary()
        xlib = ExperienceLibrary.load_from_file(str(path), theorem_lib=tlib)
        if xlib.count == 0:
            return {"action": "experience_lifecycle", "skipped": "empty_library"}

        critical = [s for s in report.suggestions if s.severity == "critical"]
        if not critical:
            return {"action": "experience_lifecycle", "skipped": "no_critical"}

        candidates = sorted(
            xlib._experiences.items(),
            key=lambda item: item[1].validity_end,
        )[:3]
        if not candidates:
            return {"action": "experience_lifecycle", "skipped": "no_candidates"}
        eval_results = {eid: False for eid, _ in candidates}
        result = xlib.lifecycle_pass(eval_results)
        result["demoted_ids"] = list(eval_results.keys())
        xlib.save_to_file(str(path))
        action = {"action": "experience_lifecycle", **result}
        _append_audit(action)
        return action
    except Exception as exc:
        logger.debug("experience lifecycle action skipped: %s", exc)
        return {"action": "experience_lifecycle", "error": str(exc)}


def apply_hard_feedback(report: FeedbackReport | None = None) -> dict[str, Any]:
    """Apply bounded hard feedback from LangFuse score analysis."""
    if not hard_feedback_enabled():
        return {"applied": False, "reason": "disabled"}
    if not _should_run():
        return {"applied": False, "reason": "throttled"}

    if report is None:
        report = analyse_scores()

    if not report.suggestions:
        _mark_run({"applied": False, "reason": "no_suggestions"})
        return {"applied": False, "reason": "no_suggestions"}

    actions: list[dict[str, Any]] = []
    for suggestion in report.suggestions:
        if suggestion.metric_name in ("memory_effectiveness", "memory_benchmark.pass_rate"):
            actions.append(_apply_memory_action(suggestion))

    if any(s.severity == "critical" for s in report.suggestions):
        actions.append(_apply_experience_lifecycle(report))

    summary = {
        "applied": bool(actions),
        "actions": actions,
        "suggestion_count": len(report.suggestions),
    }
    _mark_run(summary)
    return summary


__all__ = ["apply_hard_feedback", "hard_feedback_enabled"]
