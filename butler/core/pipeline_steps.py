"""Named ContextPipeline steps with per-step timing (LobeHub subset)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class PipelineStep:
    name: str
    run: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]


def run_pipeline_steps(
    messages: list[dict[str, Any]],
    steps: list[PipelineStep],
    *,
    diagnostics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    out = list(messages)
    timings: dict[str, float] = {}
    for step in steps:
        t0 = time.perf_counter()
        out = step.run(out)
        timings[step.name] = round((time.perf_counter() - t0) * 1000.0, 2)
    if diagnostics is not None:
        prev = diagnostics.get("context_pipeline_steps")
        if isinstance(prev, dict):
            merged = dict(prev)
            merged.update(timings)
            diagnostics["context_pipeline_steps"] = merged
        else:
            diagnostics["context_pipeline_steps"] = timings
    return out


def format_pipeline_step_lines(diagnostics: dict[str, Any] | None) -> list[str]:
    if not isinstance(diagnostics, dict):
        return []
    steps = diagnostics.get("context_pipeline_steps")
    if not isinstance(steps, dict) or not steps:
        return []
    lines = ["ContextPipeline 步骤耗时 (ms):"]
    for name in sorted(steps):
        ms = steps[name]
        lines.append(f"  {name}: {ms}")
    return lines


__all__ = ["PipelineStep", "format_pipeline_step_lines", "run_pipeline_steps"]
