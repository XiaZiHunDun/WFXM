"""Shared helpers for Butler vs Claude Code head-to-head scenarios."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_NAME = "灵文1号"


@dataclass(frozen=True)
class HeadToHeadScenario:
    id: str
    fixture: Path
    session: str
    chat_id: str
    category: str
    task: str
    context: str
    pytest_args: list[str]
    cc_prompt_template: str  # {ws}, {fail_tail}


def seed_head_to_head_project_yaml(ws: Path, pytest_args: list[str]) -> None:
    """Minimal project.yaml so auto-verify runs fixture-scoped pytest, not LingWen suite."""
    args = " ".join(pytest_args)
    content = (
        "name: head-to-head-fixture\n"
        "type: software\n"
        "workspace: .\n"
        "dev:\n"
        f'  test_command: python3 -m pytest {args} -q --tb=short\n'
        '  lint_command: "true"\n'
    )
    (ws / "project.yaml").write_text(content, encoding="utf-8")


def reset_workspace(scenario: HeadToHeadScenario) -> Path:
    broken = scenario.fixture / "broken"
    ws = scenario.fixture / "ws"
    if ws.exists():
        shutil.rmtree(ws)
    shutil.copytree(broken, ws)
    return ws.resolve()


def seed_read_state(ws: Path, session_key: str) -> None:
    try:
        from butler.dev_engine.b9_delegate_gate import seed_b9_workspace_read_state

        seed_b9_workspace_read_state(ws, session_key=session_key, max_depth=2)
    except Exception:
        pass


def wait_task(task_id: str, *, timeout_s: float = 600) -> dict[str, Any]:
    from butler.runtime.task_store import get_task

    deadline = time.time() + timeout_s
    rec: dict[str, Any] = {}
    while time.time() < deadline:
        rec = get_task(task_id) or {}
        if str(rec.get("status") or "") in ("completed", "failed"):
            return rec
        time.sleep(2)
    return rec


def run_pytest(ws: Path, pytest_args: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(
        ["python3", "-m", "pytest", *pytest_args, "-q"],
        cwd=ws,
        capture_output=True,
        text=True,
        timeout=180,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out.strip()[-500:]


def _configure_dev_env() -> None:
    """Head-to-head: force dev harness env (do not inherit broad verify levels from .env)."""
    os.environ["BUTLER_ENABLE_TERMINAL"] = "1"
    os.environ["BUTLER_TERMINAL_PROFILE"] = "dev"
    os.environ["BUTLER_DEV_ENGINE"] = "1"
    os.environ["BUTLER_DEV_AUTO_VERIFY"] = "1"
    os.environ["BUTLER_DEV_AUTO_VERIFY_LEVELS"] = "test"


def _load_delegate_metrics(task_id: str, session_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort dev_engine / iterations from report after async delegate."""
    out: dict[str, Any] = {}
    de = payload.get("dev_engine")
    if isinstance(de, dict):
        out.update(de)
    try:
        from butler.report import get_last_report

        report = get_last_report(session_key)
        if report is not None and str(getattr(report, "task_id", "") or "") == task_id:
            out.setdefault("verify_passed", report.success)
            out["iterations"] = int(getattr(report, "iterations", 0) or 0)
            out["tool_calls"] = int(getattr(report, "tool_calls", 0) or 0)
            issues = getattr(report, "issues", None) or []
            if any("DEV_VERIFY_GATE" in str(i) for i in issues):
                out["verify_passed"] = False
    except Exception:
        pass
    return out


def run_butler(scenario: HeadToHeadScenario, *, live: bool = True) -> dict[str, Any]:
    ws = reset_workspace(scenario)
    seed_head_to_head_project_yaml(ws, scenario.pytest_args)
    ok_before, _ = run_pytest(ws, scenario.pytest_args)
    if ok_before:
        return {"ok": False, "reason": "fixture_already_green", "side": "butler"}

    if live:
        _configure_dev_env()

    from butler.execution_context import use_execution_context
    from butler.project.manager import get_project_manager
    from butler.tools.delegate_impl import _orchestrator_for_tool
    from butler.tools.registry import dispatch_tool

    pm = get_project_manager()
    proj = pm.get_project(PROJECT_NAME)
    if proj is None:
        return {"ok": False, "reason": "project_not_found", "side": "butler"}

    orig_workspace = proj.workspace
    orch = _orchestrator_for_tool(channel="cli")
    t0 = time.time()
    try:
        proj.workspace = ws
        pm.switch_project_for_chat(
            platform="cli",
            chat_id=scenario.chat_id,
            name=PROJECT_NAME,
        )
        os.environ["BUTLER_TOOL_SAFE_ROOT"] = str(ws)
        seed_read_state(ws, scenario.session)
        with use_execution_context(orch, session_key=scenario.session):
            raw = dispatch_tool(
                "delegate_task",
                {
                    "role": "dev",
                    "category": scenario.category,
                    "task": scenario.task,
                    "context": f"{scenario.context}\n\nWorkspace: {ws}",
                },
            )
    finally:
        proj.workspace = orig_workspace
        os.environ.pop("BUTLER_TOOL_SAFE_ROOT", None)

    elapsed_s = round(time.time() - t0, 1)
    try:
        payload = json.loads(raw) if isinstance(raw, str) else {}
    except json.JSONDecodeError:
        payload = {"raw": str(raw)[:500]}

    task_id = str(payload.get("task_id") or "")
    metrics: dict[str, Any] = {}
    if task_id:
        rec = wait_task(task_id)
        if rec:
            payload["success"] = rec.get("success")
            payload["headline"] = rec.get("report_headline") or payload.get("headline")
        metrics = _load_delegate_metrics(task_id, scenario.session, payload)

    dev_engine = metrics if metrics else (
        payload.get("dev_engine") if isinstance(payload.get("dev_engine"), dict) else {}
    )
    pytest_green, pytest_tail = run_pytest(ws, scenario.pytest_args)

    iterations = int(metrics.get("iterations") or payload.get("iterations") or 0)
    tool_calls = int(metrics.get("tool_calls") or payload.get("tool_calls") or 0)
    verify_passed = dev_engine.get("verify_passed")
    if verify_passed is None:
        verify_passed = bool(payload.get("success")) and pytest_green

    return {
        "side": "butler",
        "scenario": scenario.id,
        "workspace": str(ws),
        "task_id": task_id,
        "delegate_success": bool(payload.get("success")),
        "verify_passed": bool(verify_passed),
        "pytest_green": pytest_green,
        "pytest_tail": pytest_tail,
        "elapsed_seconds": elapsed_s,
        "iterations": iterations,
        "tool_calls": tool_calls,
        "headline": str(payload.get("headline") or ""),
    }


def run_cc(scenario: HeadToHeadScenario, *, live: bool = True) -> dict[str, Any]:
    ws = reset_workspace(scenario)
    ok_before, fail_tail = run_pytest(ws, scenario.pytest_args)
    if ok_before:
        return {"ok": False, "reason": "fixture_already_green", "side": "cc"}

    prompt = scenario.cc_prompt_template.format(ws=ws, fail_tail=fail_tail)
    if not live:
        return {"side": "cc", "scenario": scenario.id, "skipped": True}

    t0 = time.time()
    proc = subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--allowed-tools",
            "Read",
            "Edit",
            "Bash",
        ],
        cwd=ws,
        capture_output=True,
        text=True,
        timeout=600,
        stdin=subprocess.DEVNULL,
    )
    elapsed_s = round(time.time() - t0, 1)
    cc_meta: dict[str, Any] = {}
    if proc.stdout.strip():
        try:
            cc_meta = json.loads(proc.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            cc_meta = {"raw": proc.stdout[-400:]}

    pytest_green, pytest_tail = run_pytest(ws, scenario.pytest_args)
    return {
        "side": "cc",
        "scenario": scenario.id,
        "workspace": str(ws),
        "pytest_green": pytest_green,
        "pytest_tail": pytest_tail,
        "elapsed_seconds": elapsed_s,
        "num_turns": int(cc_meta.get("num_turns") or 0),
        "duration_ms": int(cc_meta.get("duration_ms") or 0),
        "cc_error": bool(cc_meta.get("is_error")),
        "cc_result": str(cc_meta.get("result") or "")[:200],
        "exit_code": proc.returncode,
        "stderr_tail": (proc.stderr or "")[-300:],
    }


def run_scenario(
    scenario: HeadToHeadScenario,
    *,
    live: bool = True,
    butler_only: bool = False,
    cc_only: bool = False,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "scenario": scenario.id,
        "fixture": str(scenario.fixture),
        "live": live,
    }
    if not cc_only:
        out["butler"] = run_butler(scenario, live=live)
    if not butler_only:
        out["cc"] = run_cc(scenario, live=live)
    b = out.get("butler") or {}
    c = out.get("cc") or {}
    out["summary"] = {
        "butler_pytest_green": b.get("pytest_green"),
        "cc_pytest_green": c.get("pytest_green"),
        "butler_elapsed_s": b.get("elapsed_seconds"),
        "cc_elapsed_s": c.get("elapsed_seconds"),
        "butler_iterations": b.get("iterations"),
        "cc_num_turns": c.get("num_turns"),
    }
    return out
