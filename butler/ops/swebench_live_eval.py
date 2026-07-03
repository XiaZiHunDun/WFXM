"""SWE-bench Lite weekly LIVE/oracle subset evaluation (phase 3).

Rotates a small instance subset (default 3/week) and scores separately from
oracle B8 aggregate as ``B8_swebench_live.*``.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SWELiveResult:
    instance_id: str
    category: str
    passed: bool
    mode: str
    failure_reasons: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "category": self.category,
            "passed": self.passed,
            "mode": self.mode,
            "failure_reasons": self.failure_reasons,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }


@dataclass
class SWELiveReport:
    results: list[SWELiveResult] = field(default_factory=list)
    mode: str = "oracle"
    week: int = 0

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def swe_live_count() -> int:
    try:
        from butler.env_parse import int_env

        return int_env("BUTLER_EVAL_SWE_LIVE_COUNT", 3, min=1, max=15)
    except ValueError:
        return 3


def select_weekly_instances(count: int | None = None) -> list[Any]:
    """Pick a rotating SWE subset based on ISO week number."""
    from butler.dev_engine.swebench_lite import get_all_instances

    instances = get_all_instances()
    if not instances:
        return []
    n = count if count is not None else swe_live_count()
    import datetime as dt

    week = dt.datetime.now(dt.timezone.utc).isocalendar().week
    offset = (week * n) % len(instances)
    return [instances[(offset + i) % len(instances)] for i in range(n)]


def _instance_delegate_prompt(inst: Any) -> str:
    hint = ""
    if inst.instance_id == "SWE-015":
        hint = (
            "\n\nHint: after sorting by priority ascending, remove index 0 (pop(0)), "
            "not pop() which removes the last element."
        )
    elif inst.instance_id == "SWE-012":
        hint = (
            "\n\nHint: sort_items([]) already returns []; the bug is in test_sorter.py — "
            "fix test_sort_empty assertion (is None → == []), not sorter.py."
        )
    return (
        f"Fix the issue in this repository.\n\n"
        f"# {inst.issue_title}\n\n{inst.issue_body}\n\n"
        f"Apply the minimal patch and ensure tests pass.{hint}"
    )


def build_swe_delegate_context(inst: Any) -> str:
    from butler.dev_engine.swe_curriculum import (
        build_swe_playbook_block,
        format_swe_replay_block,
    )

    files = ", ".join(sorted(inst.files.keys()))
    parts: list[str] = []
    # Inject full replay on attempt 0 — retries still get replay via llm_delegate_benchmark.
    replay = format_swe_replay_block(inst.instance_id)
    if replay:
        parts.append(replay)
    else:
        playbook = build_swe_playbook_block(inst.instance_id)
        if playbook:
            parts.append(playbook)
    parts.append(
        f"SWE-bench instance {inst.instance_id} ({inst.category}, {inst.difficulty}).\n"
        f"Repo files: {files}\n"
        "Workflow: read issue → patch implementation → "
        "`python -m pytest _swe_test.py -q` until green.\n"
        "Pre-loaded sources may appear in <benchmark-workspace-files>."
    )
    return "\n\n".join(parts)


def _swe_instance_to_task_spec(inst: Any) -> Any:
    from butler.dev_engine.b9_delegate_gate import SWE_LIVE_CATEGORY
    from butler.dev_engine.llm_delegate_benchmark import B9TaskSpec

    def setup(ws: Path) -> None:
        inst.setup_workspace(ws)

    def oracle_apply(ws: Path) -> None:
        inst.apply_oracle(ws)

    def verify(ws: Path) -> tuple[bool, str]:
        from butler.ops.swebench_live_eval_ops import verify_swe_instance_safe

        return verify_swe_instance_safe(inst, ws)

    return B9TaskSpec(
        task_id=inst.instance_id,
        description=f"SWE live: {inst.issue_title}",
        delegate_prompt=_instance_delegate_prompt(inst),
        setup=setup,
        verify=verify,
        oracle_apply=oracle_apply,
        benchmark_category=SWE_LIVE_CATEGORY,
        benchmark_context_extra=build_swe_delegate_context(inst),
    )


def resolve_swe_live_mode() -> str:
    if os.getenv("BUTLER_EVAL_LLM_BENCHMARK", "0").strip() in ("1", "true", "yes"):
        return "live"
    return "oracle"


def run_swe_instance(
    inst: Any,
    workspace: Path,
    *,
    mode: str | None = None,
) -> SWELiveResult:
    from butler.dev_engine.llm_delegate_benchmark import B9Mode, run_b9_task

    mode_str = mode or resolve_swe_live_mode()
    b9_mode = B9Mode.LIVE if mode_str == "live" else B9Mode.ORACLE
    spec = _swe_instance_to_task_spec(inst)
    t0 = time.time()
    from butler.dev_engine.b9_delegate_gate import benchmark_verify_context

    with benchmark_verify_context(spec.verify):
        b9_result = run_b9_task(spec, workspace, mode=b9_mode)
    return SWELiveResult(
        instance_id=inst.instance_id,
        category=inst.category,
        passed=b9_result.passed,
        mode=mode_str,
        failure_reasons=b9_result.failure_reasons,
        elapsed_seconds=time.time() - t0,
    )


def run_swebench_live_benchmark(
    workspace: Path | None = None,
    *,
    instances: list[Any] | None = None,
    mode: str | None = None,
) -> SWELiveReport:
    import datetime as dt
    import tempfile

    mode_str = mode or resolve_swe_live_mode()
    report = SWELiveReport(
        mode=mode_str,
        week=dt.datetime.now(dt.timezone.utc).isocalendar().week,
    )
    inst_list = instances if instances is not None else select_weekly_instances()

    for inst in inst_list:
        if workspace:
            ws = workspace / inst.instance_id
            ws.mkdir(parents=True, exist_ok=True)
        else:
            ws = Path(tempfile.mkdtemp(prefix=f"swe_{inst.instance_id}_"))
        report.results.append(run_swe_instance(inst, ws, mode=mode_str))

    return report


def push_swebench_live_scores(report: SWELiveReport) -> dict[str, Any]:
    from butler.ops.eval_bridge import push_scores, swebench_live_to_scores

    scores = swebench_live_to_scores(report)
    push_report = push_scores(scores)
    return {
        "scores_pushed": push_report.scores_pushed,
        "pass_rate": report.pass_rate,
        "mode": report.mode,
        "week": report.week,
    }


__all__ = [
    "SWELiveReport",
    "SWELiveResult",
    "build_swe_delegate_context",
    "push_swebench_live_scores",
    "resolve_swe_live_mode",
    "run_swebench_live_benchmark",
    "select_weekly_instances",
    "swe_live_count",
]
