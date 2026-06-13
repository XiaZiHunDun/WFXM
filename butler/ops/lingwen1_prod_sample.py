"""Run 2–3 real LingWen1 workspace delegate samples (production-shaped, not drill)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from butler.ops.lingwen1_delegate_drill import LINGWEN_PROJECT_NAME

SAMPLE_SESSION = "cli:lingwen1-prod-sample"


@dataclass(frozen=True)
class LingWen1ProdSample:
    sample_id: str
    task: str
    context: str
    expect_success: bool = True


LINGWEN1_PROD_SAMPLES: tuple[LingWen1ProdSample, ...] = (
    LingWen1ProdSample(
        sample_id="lingwen1-sample-demo-import",
        task=(
            "Verify demo/hello.py in this project: read_file demo/hello.py, then run "
            "terminal: python -c \"from demo.hello import add, greet; "
            "assert add(3.5, 4.5) == 8.0; assert '灵文1号' in greet('主公')\". "
            "Do not edit any files."
        ),
        context="Production-shaped read+verify on LingWen1 demo module.",
        expect_success=True,
    ),
    LingWen1ProdSample(
        sample_id="lingwen1-sample-constants-comment",
        task=(
            "Read constants.py. If the file has no module docstring, patch to add "
            "a one-line module docstring at the top. Then run terminal: "
            "python -c \"import constants; assert constants.MAX_RETRIES == 3\". "
            "Only edit constants.py."
        ),
        context="Small safe edit on LingWen1 constants.py with import verify.",
        expect_success=True,
    ),
    LingWen1ProdSample(
        sample_id="lingwen1-sample-validate-progress",
        task=(
            "Run novel-factory/scripts/validate_progress.py via terminal from project root. "
            "Read the output; if exit code is 0, summarize pass. If non-zero, read "
            "workflow_state.json and validate_progress.py — report root cause only, "
            "do not edit novel-factory content unless user approves."
        ),
        context="Production-shaped novel-factory progress validation (read-only preferred).",
        expect_success=True,
    ),
)


def _project_workspace() -> Path | None:
    from butler.project.manager import get_project_manager

    pm = get_project_manager()
    proj = pm.get_project(LINGWEN_PROJECT_NAME)
    if proj is None or not getattr(proj, "workspace", None):
        return None
    try:
        return Path(proj.workspace).resolve()
    except (TypeError, ValueError, OSError):
        return None


def run_lingwen1_prod_sample(
    sample: LingWen1ProdSample,
    *,
    live: bool = True,
) -> dict[str, Any]:
    """Execute one delegate_task on LingWen1 real workspace."""
    ws = _project_workspace()
    if ws is None or not ws.is_dir():
        return {
            "ok": False,
            "sample_id": sample.sample_id,
            "reason": "project_workspace_missing",
            "project": LINGWEN_PROJECT_NAME,
        }

    if live:
        os.environ["BUTLER_EVAL_LLM_BENCHMARK"] = "1"
        os.environ["BUTLER_ENABLE_TERMINAL"] = "1"
        os.environ["BUTLER_TERMINAL_PROFILE"] = "dev"

    from butler.execution_context import use_execution_context
    from butler.project.manager import get_project_manager
    from butler.tools.delegate_impl import _orchestrator_for_tool
    from butler.tools.registry import dispatch_tool

    pm = get_project_manager()
    proj = pm.get_project(LINGWEN_PROJECT_NAME)
    if proj is None:
        return {"ok": False, "sample_id": sample.sample_id, "reason": "project_not_found"}

    orig_workspace = proj.workspace
    orch = _orchestrator_for_tool(channel="cli")
    try:
        proj.workspace = ws
        pm.switch_project_for_chat(
            platform="cli",
            chat_id="lingwen1-prod-sample",
            name=LINGWEN_PROJECT_NAME,
        )
        os.environ["BUTLER_TOOL_SAFE_ROOT"] = str(ws)
        with use_execution_context(orch, session_key=SAMPLE_SESSION):
            raw = dispatch_tool(
                "delegate_task",
                {
                    "role": "dev",
                    "task": sample.task,
                    "context": sample.context,
                },
            )
    finally:
        proj.workspace = orig_workspace
        if "BUTLER_TOOL_SAFE_ROOT" in os.environ:
            del os.environ["BUTLER_TOOL_SAFE_ROOT"]

    try:
        payload = json.loads(raw) if isinstance(raw, str) else {}
    except json.JSONDecodeError:
        payload = {"raw": str(raw)[:500]}

    success = bool(payload.get("success"))
    dev_engine = payload.get("dev_engine") if isinstance(payload.get("dev_engine"), dict) else {}
    return {
        "ok": True,
        "sample_id": sample.sample_id,
        "project": LINGWEN_PROJECT_NAME,
        "workspace": str(ws),
        "delegate_success": success,
        "verify_passed": dev_engine.get("verify_passed"),
        "expect_success": sample.expect_success,
        "matched_expectation": success == sample.expect_success,
        "delegate_task_id": str(payload.get("task_id") or ""),
        "tools_used": payload.get("tools_used") or [],
        "headline": payload.get("headline", ""),
        "capture_source_expected": "delegate_pipeline",
    }


def run_lingwen1_prod_samples(
    *,
    live: bool = True,
    sample_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Run all (or selected) LingWen1 production-shaped delegate samples."""
    want = set(sample_ids) if sample_ids else None
    results: list[dict[str, Any]] = []
    for sample in LINGWEN1_PROD_SAMPLES:
        if want is not None and sample.sample_id not in want:
            continue
        results.append(run_lingwen1_prod_sample(sample, live=live))
    passed = sum(1 for r in results if r.get("matched_expectation"))
    total = len(results)
    return {
        "project": LINGWEN_PROJECT_NAME,
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "results": results,
    }


__all__ = [
    "LINGWEN1_PROD_SAMPLES",
    "LingWen1ProdSample",
    "SAMPLE_SESSION",
    "run_lingwen1_prod_sample",
    "run_lingwen1_prod_samples",
]
