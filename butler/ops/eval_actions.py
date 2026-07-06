"""Hard feedback actions from eval scores (O6) with audit trail."""

from __future__ import annotations

from butler.env_parse import float_env
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, cast

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
        return cast(float, max(0.25, hours) * 3600.0)
    except ValueError:
        return 3600.0


def _audit_path() -> Path:
    from butler.config import get_butler_home

    return cast(Path, get_butler_home()) / "audit" / "eval_feedback.jsonl"


def _state_path() -> Path:
    from butler.config import get_butler_home

    return cast(Path, get_butler_home()) / "config" / _STATE_PATH_NAME


def _append_audit(record: dict[str, Any]) -> None:
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record.setdefault("ts", time.time())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_eval_feedback(record: dict[str, Any]) -> None:
    """Public append for production/G1-04 evidence rows."""
    _append_audit(record)


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


def _apply_dev_benchmark_action(suggestion: FeedbackSuggestion) -> dict[str, Any]:
    from butler.ops.eval_config_overrides import adjust_dev_coding_guidance

    action = adjust_dev_coding_guidance(strict=True, max_cases=8)
    action["metric"] = suggestion.metric_name
    action["metric_value"] = suggestion.metric_value
    _append_audit(action)
    return cast(dict[str, Any], action)


def _apply_tool_selection_action(suggestion: FeedbackSuggestion) -> dict[str, Any]:
    from butler.ops.eval_config_overrides import adjust_delegate_routing

    action = adjust_delegate_routing(enable_hint=True)
    action["metric"] = suggestion.metric_name
    action["metric_value"] = suggestion.metric_value
    _append_audit(action)
    return cast(dict[str, Any], action)


def _apply_llm_benchmark_action(suggestion: FeedbackSuggestion) -> dict[str, Any]:
    from butler.ops.eval_config_overrides import adjust_delegate_rescue

    action = adjust_delegate_rescue()
    action["metric"] = suggestion.metric_name
    action["metric_value"] = suggestion.metric_value
    _append_audit(action)
    return cast(dict[str, Any], action)


def _apply_experience_lifecycle(report: FeedbackReport) -> dict[str, Any]:
    """Demote experiences when dev/memory benchmarks are critically low."""
    from butler.ops.eval_actions_ops import apply_experience_lifecycle_action_safe

    action, err = apply_experience_lifecycle_action_safe(report)
    if err is not None:
        return {"action": "experience_lifecycle", "error": err}
    if action is None:
        return {"action": "experience_lifecycle", "error": "unknown"}
    if action.get("demoted_ids") is not None:
        _append_audit(action)
    return cast(dict[str, Any], action)


def maybe_apply_b9_live_rescue(
    report: Any,
    *,
    min_solvable_rate: float | None = None,
) -> dict[str, Any] | None:
    """Persist delegate_rescue overrides when B9 LIVE solvable pass rate is low."""
    if min_solvable_rate is None:
        min_solvable_rate = float_env("BUTLER_EVAL_B9_RESCUE_PASS_RATE_MIN", 0.5)
    stuck_ids = {"B9L_stuck_unsolvable"}
    results = list(getattr(report, "results", []) or [])
    solvable = [r for r in results if getattr(r, "task_id", "") not in stuck_ids]
    if not solvable:
        return None
    passed = sum(1 for r in solvable if getattr(r, "passed", False))
    rate = passed / len(solvable)
    if rate >= min_solvable_rate:
        return None
    from butler.ops.eval_config_overrides import adjust_delegate_rescue

    action = adjust_delegate_rescue()
    action.update({
        "trigger": "b9_live_low_pass",
        "solvable_pass_rate": round(rate, 4),
        "solvable_passed": passed,
        "solvable_total": len(solvable),
    })
    _append_audit(action)
    logger.info(
        "B9 LIVE solvable pass rate %.0f%% < %.0f%% — applied delegate_rescue overrides",
        rate * 100,
        min_solvable_rate * 100,
    )
    return cast(dict[str, Any], action)


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
        elif suggestion.metric_name == "dev_benchmark.pass_rate":
            actions.append(_apply_dev_benchmark_action(suggestion))
        elif suggestion.metric_name == "llm_benchmark.pass_rate":
            actions.append(_apply_llm_benchmark_action(suggestion))
        elif suggestion.metric_name in ("tool_selection", "delegate_routing"):
            actions.append(_apply_tool_selection_action(suggestion))

    if any(s.severity == "critical" for s in report.suggestions):
        actions.append(_apply_experience_lifecycle(report))

    summary = {
        "applied": bool(actions),
        "actions": actions,
        "suggestion_count": len(report.suggestions),
    }
    _mark_run(summary)
    return summary


__all__ = ["append_eval_feedback", "apply_hard_feedback", "hard_feedback_enabled", "maybe_apply_b9_live_rescue"]
