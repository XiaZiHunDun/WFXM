"""DevEngine effectiveness metrics — runtime measurement of development capability.

Formal model:
  Layer 2: Runtime metrics — per-task outcome tracking + aggregate statistics
  Layer 3: Comparative benchmarks — standardized tasks with expected outcomes

Metrics collected per task:
  - Outcome: DONE | STUCK | ABANDONED
  - Edit precision: edits followed by verify_pass / total edits
  - Fix convergence: fix loops ending in DONE / total fix entries
  - First-pass rate: tasks reaching DONE without FIX / total DONE
  - Iteration efficiency: average iterations to completion
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TaskOutcome(str, Enum):
    DONE = "DONE"
    STUCK = "STUCK"
    ABANDONED = "ABANDONED"
    IN_PROGRESS = "IN_PROGRESS"


@dataclass
class TransitionRecord:
    """Single state transition event for metrics analysis."""

    from_phase: str
    event: str
    to_phase: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class DevTaskMetrics:
    """Per-task effectiveness metrics."""

    task_id: str = ""
    task_description: str = ""
    outcome: TaskOutcome = TaskOutcome.IN_PROGRESS
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0

    total_iterations: int = 0
    total_edits: int = 0
    total_rollbacks: int = 0

    verify_attempts: int = 0
    verify_passes: int = 0
    verify_fails: int = 0

    fix_entries: int = 0
    fix_exits_to_verify: int = 0
    fix_exits_to_plan: int = 0

    entered_fix_loop: bool = False
    transitions: list[TransitionRecord] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def edit_precision(self) -> float:
        """Edits that led to verify_pass / total edits. Higher = better."""
        if self.total_edits == 0:
            return 0.0
        return self.verify_passes / self.total_edits

    @property
    def first_pass(self) -> bool:
        """True if task completed without entering FIX loop."""
        return self.outcome == TaskOutcome.DONE and not self.entered_fix_loop

    @property
    def fix_convergence(self) -> float:
        """Fix loops that converged to verify / total fix entries."""
        if self.fix_entries == 0:
            return 1.0
        return self.fix_exits_to_verify / self.fix_entries

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_description": self.task_description[:200],
            "outcome": self.outcome.value,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "total_iterations": self.total_iterations,
            "total_edits": self.total_edits,
            "total_rollbacks": self.total_rollbacks,
            "verify_attempts": self.verify_attempts,
            "verify_passes": self.verify_passes,
            "verify_fails": self.verify_fails,
            "fix_entries": self.fix_entries,
            "entered_fix_loop": self.entered_fix_loop,
            "edit_precision": round(self.edit_precision, 3),
            "first_pass": self.first_pass,
            "fix_convergence": round(self.fix_convergence, 3),
        }


@dataclass
class AggregateMetrics:
    """Aggregated metrics across all completed tasks."""

    total_tasks: int = 0
    completed_tasks: int = 0
    stuck_tasks: int = 0
    abandoned_tasks: int = 0
    in_progress_tasks: int = 0

    completion_rate: float = 0.0
    stuck_rate: float = 0.0
    first_pass_rate: float = 0.0
    avg_edit_precision: float = 0.0
    avg_fix_convergence: float = 0.0
    avg_iterations_to_done: float = 0.0
    avg_edits_to_done: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "stuck_tasks": self.stuck_tasks,
            "abandoned_tasks": self.abandoned_tasks,
            "in_progress_tasks": self.in_progress_tasks,
            "completion_rate": round(self.completion_rate, 3),
            "stuck_rate": round(self.stuck_rate, 3),
            "first_pass_rate": round(self.first_pass_rate, 3),
            "avg_edit_precision": round(self.avg_edit_precision, 3),
            "avg_fix_convergence": round(self.avg_fix_convergence, 3),
            "avg_iterations_to_done": round(self.avg_iterations_to_done, 1),
            "avg_edits_to_done": round(self.avg_edits_to_done, 1),
        }


class MetricsCollector:
    """Collects and aggregates DevEngine effectiveness metrics.

    Lifecycle:
      1. on_task_start(task_id, description) — when DevState is created
      2. on_transition(task_id, from_phase, event, to_phase) — each transition
      3. on_task_end(task_id, outcome) — when task reaches terminal state

    Thread-safe via dict-per-task isolation.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, DevTaskMetrics] = {}
        self._completed: list[DevTaskMetrics] = []

    def on_task_start(self, task_id: str, description: str = "") -> DevTaskMetrics:
        metrics = DevTaskMetrics(task_id=task_id, task_description=description)
        self._tasks[task_id] = metrics
        return metrics

    def on_transition(
        self,
        task_id: str,
        from_phase: str,
        event: str,
        to_phase: str,
    ) -> None:
        m = self._tasks.get(task_id)
        if m is None:
            return

        m.transitions.append(TransitionRecord(
            from_phase=from_phase,
            event=event,
            to_phase=to_phase,
        ))
        m.total_iterations += 1

        if event == "edit_success":
            m.total_edits += 1

        if event == "verify_pass":
            m.verify_attempts += 1
            m.verify_passes += 1
        elif event == "verify_fail":
            m.verify_attempts += 1
            m.verify_fails += 1

        if to_phase == "FIX":
            m.fix_entries += 1
            m.entered_fix_loop = True
        if from_phase == "FIX" and event == "fix_applied":
            m.fix_exits_to_verify += 1
        if from_phase == "FIX" and event == "fix_rollback":
            m.fix_exits_to_plan += 1
            m.total_rollbacks += 1

        if to_phase == "DONE":
            m.outcome = TaskOutcome.DONE
            m.end_time = time.time()
            self._finalize(task_id)
        elif to_phase == "STUCK":
            m.outcome = TaskOutcome.STUCK
            m.end_time = time.time()
            self._finalize(task_id)

    def on_task_abandon(self, task_id: str) -> None:
        m = self._tasks.get(task_id)
        if m is None:
            return
        m.outcome = TaskOutcome.ABANDONED
        m.end_time = time.time()
        self._finalize(task_id)

    def _finalize(self, task_id: str) -> None:
        m = self._tasks.pop(task_id, None)
        if m is not None:
            self._completed.append(m)

    def get_task_metrics(self, task_id: str) -> DevTaskMetrics | None:
        return self._tasks.get(task_id)

    def aggregate(self) -> AggregateMetrics:
        all_tasks = self._completed + list(self._tasks.values())
        if not all_tasks:
            return AggregateMetrics()

        agg = AggregateMetrics(total_tasks=len(all_tasks))

        done_tasks: list[DevTaskMetrics] = []
        for t in all_tasks:
            if t.outcome == TaskOutcome.DONE:
                agg.completed_tasks += 1
                done_tasks.append(t)
            elif t.outcome == TaskOutcome.STUCK:
                agg.stuck_tasks += 1
            elif t.outcome == TaskOutcome.ABANDONED:
                agg.abandoned_tasks += 1
            else:
                agg.in_progress_tasks += 1

        finished = agg.completed_tasks + agg.stuck_tasks + agg.abandoned_tasks
        if finished > 0:
            agg.completion_rate = agg.completed_tasks / finished
            agg.stuck_rate = agg.stuck_tasks / finished

        if done_tasks:
            first_pass_count = sum(1 for t in done_tasks if t.first_pass)
            agg.first_pass_rate = first_pass_count / len(done_tasks)
            agg.avg_iterations_to_done = (
                sum(t.total_iterations for t in done_tasks) / len(done_tasks)
            )
            agg.avg_edits_to_done = (
                sum(t.total_edits for t in done_tasks) / len(done_tasks)
            )

        tasks_with_edits = [t for t in all_tasks if t.total_edits > 0]
        if tasks_with_edits:
            agg.avg_edit_precision = (
                sum(t.edit_precision for t in tasks_with_edits) / len(tasks_with_edits)
            )

        tasks_with_fix = [t for t in all_tasks if t.fix_entries > 0]
        if tasks_with_fix:
            agg.avg_fix_convergence = (
                sum(t.fix_convergence for t in tasks_with_fix) / len(tasks_with_fix)
            )

        return agg

    def export_json(self) -> str:
        return json.dumps({
            "aggregate": self.aggregate().to_dict(),
            "completed_tasks": [t.to_dict() for t in self._completed[-50:]],
            "active_tasks": [t.to_dict() for t in self._tasks.values()],
        }, ensure_ascii=False, indent=2)

    def save_to_file(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.export_json(), encoding="utf-8")

    def load_from_file(self, path: Path) -> None:
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for td in data.get("completed_tasks", []):
                m = DevTaskMetrics(
                    task_id=td.get("task_id", ""),
                    task_description=td.get("task_description", ""),
                    outcome=TaskOutcome(td.get("outcome", "DONE")),
                    total_iterations=td.get("total_iterations", 0),
                    total_edits=td.get("total_edits", 0),
                    total_rollbacks=td.get("total_rollbacks", 0),
                    verify_attempts=td.get("verify_attempts", 0),
                    verify_passes=td.get("verify_passes", 0),
                    verify_fails=td.get("verify_fails", 0),
                    fix_entries=td.get("fix_entries", 0),
                    fix_exits_to_verify=td.get("fix_entries", 0),
                    entered_fix_loop=td.get("entered_fix_loop", False),
                )
                m.end_time = m.start_time + td.get("elapsed_seconds", 0)
                self._completed.append(m)
        except Exception as exc:
            logger.warning("Failed to load metrics: %s", exc)


# ── Global collector singleton ──────────────────────────────────

_global_collector: MetricsCollector | None = None


def get_collector() -> MetricsCollector:
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector()
    return _global_collector


def reset_collector() -> None:
    global _global_collector
    _global_collector = MetricsCollector()
