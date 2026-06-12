"""Run a real dev delegate against an isolated LingWen1-shaped drill workspace."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

LINGWEN_PROJECT_NAME = "灵文1号"
DRILL_TASK_ID_PREFIX = "lingwen1-delegate-drill"
DRILL_SESSION = "cli:lingwen1-drill"


def drill_workspace_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "drill" / "lingwen1-demo-add"


def setup_drill_workspace(*, force: bool = False) -> Path:
    """Create isolated demo/hello.py with broken add() + pytest."""
    ws = drill_workspace_path()
    if force and ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True, exist_ok=True)
    demo = ws / "demo"
    demo.mkdir(exist_ok=True)
    (demo / "__init__.py").write_text("", encoding="utf-8")
    (demo / "hello.py").write_text(
        '"""LingWen1 drill — add() intentionally wrong."""\n\n'
        "def add(a: float, b: float) -> float:\n"
        "    return a - b\n",
        encoding="utf-8",
    )
    (ws / "test_drill.py").write_text(
        "from demo.hello import add\n\n\ndef test_add_sum():\n"
        "    assert add(3.5, 4.5) == 8.0\n",
        encoding="utf-8",
    )
    return ws


def _audit_has_pipeline_capture(*, task_id: str = "") -> bool:
    from butler.ops.delegate_failure_capture import failure_audit_summary

    for rec in failure_audit_summary(limit=500).get("recent") or []:
        if str(rec.get("capture_source") or "") != "delegate_pipeline":
            continue
        if str(rec.get("project") or "") != LINGWEN_PROJECT_NAME:
            continue
        if task_id and str(rec.get("task_id") or "") != task_id:
            continue
        return True
    return False


def run_lingwen1_delegate_drill(
    *,
    live: bool = True,
    force_workspace: bool = False,
) -> dict[str, Any]:
    """Execute delegate_task on LingWen1 drill workspace (full pipeline)."""
    import json

    from butler.ops.delegate_failure_capture import capture_enabled

    if not capture_enabled():
        return {
            "ok": False,
            "reason": "capture_disabled",
            "hint": "Set BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES=1",
        }

    ws = setup_drill_workspace(force=force_workspace)
    task = (
        "Fix demo/hello.py in this LingWen1 drill workspace: add(a, b) must return a + b. "
        "test_drill.py expects add(3.5, 4.5) == 8.0. Only edit demo/hello.py."
    )
    context = (
        f"Project: {LINGWEN_PROJECT_NAME}. Drill workspace: {ws}. "
        "Run pytest via terminal on test_drill.py after patch."
    )

    if live:
        os.environ["BUTLER_EVAL_LLM_BENCHMARK"] = "1"
        os.environ["BUTLER_ENABLE_TERMINAL"] = "1"
        os.environ["BUTLER_TERMINAL_PROFILE"] = "dev"
        os.environ["BUTLER_DEV_AUTO_VERIFY"] = "1"
        if not os.environ.get("BUTLER_DEV_AUTO_VERIFY_LEVELS", "").strip():
            os.environ["BUTLER_DEV_AUTO_VERIFY_LEVELS"] = "test"

    from butler.execution_context import use_execution_context
    from butler.project.manager import get_project_manager
    from butler.tools.delegate_impl import _orchestrator_for_tool
    from butler.tools.registry import dispatch_tool

    pm = get_project_manager()
    proj = pm.get_project(LINGWEN_PROJECT_NAME)
    if proj is None:
        return {"ok": False, "reason": "project_not_found", "project": LINGWEN_PROJECT_NAME}

    orig_workspace = proj.workspace
    orch = _orchestrator_for_tool(channel="cli")
    try:
        proj.workspace = ws.resolve()
        pm.switch_project_for_chat(
            platform="cli",
            chat_id="lingwen1-drill",
            name=LINGWEN_PROJECT_NAME,
        )
        os.environ["BUTLER_TOOL_SAFE_ROOT"] = str(ws.resolve())
        with use_execution_context(orch, session_key=DRILL_SESSION):
            raw = dispatch_tool(
                "delegate_task",
                {
                    "role": "dev",
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

    delegate_task_id = str(payload.get("task_id") or "")
    dev_engine = payload.get("dev_engine") if isinstance(payload.get("dev_engine"), dict) else {}
    verify_passed = dev_engine.get("verify_passed")
    success = bool(payload.get("success"))
    pipeline_capture = _audit_has_pipeline_capture()

    return {
        "ok": True,
        "live": live,
        "workspace": str(ws),
        "delegate_success": success,
        "verify_passed": verify_passed,
        "delegate_task_id": delegate_task_id,
        "pipeline_capture_seen": pipeline_capture,
        "capture_source_expected": "delegate_pipeline",
        "project": LINGWEN_PROJECT_NAME,
        "tools_used": payload.get("tools_used") or [],
        "headline": payload.get("headline", ""),
    }


__all__ = [
    "DRILL_SESSION",
    "LINGWEN_PROJECT_NAME",
    "drill_workspace_path",
    "run_lingwen1_delegate_drill",
    "setup_drill_workspace",
]
