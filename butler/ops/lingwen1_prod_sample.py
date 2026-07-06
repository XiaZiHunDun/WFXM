"""Run 2–3 real LingWen1 workspace delegate samples (production-shaped, not drill)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from butler.ops.lingwen1_delegate_drill import LINGWEN_PROJECT_NAME

SAMPLE_SESSION = "cli:lingwen1-prod-sample"
LINGWEN_PROD_SAMPLE_CATEGORY = "lingwen-prod-sample"

LINGWEN_PROD_SAMPLE_PLAYBOOKS: dict[str, str] = {
    "lingwen1-sample-demo-import": """## PLAYBOOK demo-import (read-only code review)
1. read_file demo/hello.py only
2. Confirm in your summary: add() returns a + b (see `return a + b` in source)
3. End headline with VERIFIED when confirmed
Do NOT use terminal, run_pytest, or edit files.""",
    "lingwen1-sample-constants-comment": """## PLAYBOOK constants (idempotent)
1. read_file constants.py
2. If module docstring missing: patch ONLY to prepend a one-line module docstring before MAX_RETRIES line
3. If docstring already present and MAX_RETRIES == 3: report VERIFIED in headline — no edits
Do NOT use terminal (semicolons blocked). Do NOT write_file.""",
    "lingwen1-sample-validate-progress": """## PLAYBOOK validate_progress (read-only)
Workspace root contains novel-factory/. Run exactly one command:
terminal: python3 novel-factory/scripts/validate_progress.py
Expected stdout includes `进度验证: 通过` (exit 0). Summarize output and finish.
Do NOT edit workflow_state.json or novel-factory files. No cd/bash -c.""",
}


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
            "Read demo/hello.py and verify add(a,b) returns a+b in source. "
            "Report VERIFIED in headline. No edits, no terminal."
        ),
        context="Production-shaped read+verify on LingWen1 demo module.",
        expect_success=True,
    ),
    LingWen1ProdSample(
        sample_id="lingwen1-sample-constants-comment",
        task=(
            "Verify constants.py has module docstring and MAX_RETRIES=3. "
            "Patch only if docstring missing. No terminal."
        ),
        context="Small safe edit on LingWen1 constants.py.",
        expect_success=True,
    ),
    LingWen1ProdSample(
        sample_id="lingwen1-sample-validate-progress",
        task=(
            "Run python3 novel-factory/scripts/validate_progress.py from workspace "
            "root and confirm 进度验证: 通过 in output."
        ),
        context="Read-only novel-factory progress validation.",
        expect_success=True,
    ),
)


def build_lingwen_prod_sample_context(
    *,
    sample: LingWen1ProdSample,
    workspace: Path,
    session_key: str = SAMPLE_SESSION,
) -> str:
    from butler.dev_engine.b9_delegate_gate import prepare_b9_subagent_workspace

    parts: list[str] = []
    preamble = prepare_b9_subagent_workspace(
        workspace, session_key=session_key, max_depth=2
    )
    if preamble:
        parts.append(preamble)
    playbook = LINGWEN_PROD_SAMPLE_PLAYBOOKS.get(sample.sample_id, "")
    if playbook:
        parts.append(playbook)
    parts.append(sample.context)
    parts.append(f"Project: {LINGWEN_PROJECT_NAME}. Workspace: {workspace.resolve()}.")
    return "\n\n".join(parts)


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
        os.environ["BUTLER_DEV_AUTO_VERIFY"] = "0"

    context = build_lingwen_prod_sample_context(sample=sample, workspace=ws)
    task = sample.task

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
                    "category": LINGWEN_PROD_SAMPLE_CATEGORY,
                    "task": task,
                    "context": context,
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
    dev_engine_raw = payload.get("dev_engine")
    dev_engine: dict[str, Any] = dev_engine_raw if isinstance(dev_engine_raw, dict) else {}
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
    "LINGWEN_PROD_SAMPLE_CATEGORY",
    "LINGWEN_PROD_SAMPLE_PLAYBOOKS",
    "LingWen1ProdSample",
    "SAMPLE_SESSION",
    "build_lingwen_prod_sample_context",
    "run_lingwen1_prod_sample",
    "run_lingwen1_prod_samples",
]
