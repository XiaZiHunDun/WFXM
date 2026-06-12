"""B9 delegate harness gates — pytest success, workspace pre-read, oracle replay."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from butler.dev_engine.b9_live_tuning import B9_LIVE_CATEGORY

_B9_PREAMBLE_MAX_BYTES = 12_000
_B9_PREAMBLE_PER_FILE = 4_000


def is_b9_benchmark_category(
    category: str = "",
    category_meta: dict[str, Any] | None = None,
) -> bool:
    cat = str(category or (category_meta or {}).get("category") or "").strip()
    return cat == B9_LIVE_CATEGORY


def resolve_b9_workspace(project: Any = None) -> Path | None:
    if project is not None and getattr(project, "workspace", None):
        try:
            return Path(project.workspace).resolve()
        except (TypeError, ValueError, OSError):
            pass
    root = os.environ.get("BUTLER_TOOL_SAFE_ROOT", "").strip()
    if root:
        try:
            return Path(root).resolve()
        except (TypeError, ValueError, OSError):
            pass
    try:
        from butler.tools.path_safety import tool_safe_root

        return tool_safe_root()
    except Exception:
        return None


def apply_b9_pytest_success_gate(
    *,
    category: str = "",
    category_meta: dict[str, Any] | None = None,
    project: Any = None,
    base_success: bool,
    issues: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """B9 category: delegate success requires pytest green in workspace."""
    out = list(issues or [])
    if not base_success:
        return False, out
    if not is_b9_benchmark_category(category, category_meta):
        return True, out
    ws = resolve_b9_workspace(project)
    if ws is None:
        msg = "B9_PYTEST_GATE: workspace unresolved"
        if msg not in out:
            out.append(msg)
        return False, out
    from butler.dev_engine.b9_verify_utils import pytest_verify

    ok, tail = pytest_verify(ws)
    if ok:
        return True, out
    hint = ""
    try:
        from butler.dev_engine.b9_live_tuning import build_b9_verify_hint

        hint = build_b9_verify_hint(tail)
    except Exception:
        pass
    msg = f"B9_PYTEST_GATE: pytest not green — {(tail or 'failed')[:360]}"
    if hint:
        msg = f"{msg} | hint: {hint}"
    if msg not in out:
        out.append(msg)
    return False, out


def seed_b9_workspace_read_state(
    workspace: Path,
    *,
    session_key: str,
) -> int:
    """Pre-record read_file state for workspace .py files (READ_STATE relief)."""
    from butler.core.read_state import record_read_state

    ws = workspace.resolve()
    if not ws.is_dir():
        return 0
    count = 0
    paths = sorted(ws.glob("*.py"), key=lambda p: (p.name != "test_b9.py", p.name))
    for fp in paths:
        if not fp.is_file():
            continue
        try:
            data = fp.read_bytes()
            record_read_state(fp, fp.stat(), data, session_key=session_key)
            count += 1
        except OSError:
            continue
    return count


def build_b9_workspace_preamble(
    workspace: Path,
    *,
    max_total_bytes: int = _B9_PREAMBLE_MAX_BYTES,
    max_per_file: int = _B9_PREAMBLE_PER_FILE,
) -> str:
    """Inject workspace source snapshot so delegate can patch without READ_STATE friction."""
    ws = workspace.resolve()
    if not ws.is_dir():
        return ""
    lines = [
        "<b9-workspace-files>",
        "Pre-loaded workspace sources (also seeded in read_state — patch/write allowed):",
    ]
    used = 0
    for fp in sorted(ws.glob("*.py"), key=lambda p: (p.name != "test_b9.py", p.name)):
        if used >= max_total_bytes:
            lines.append("... (truncated)")
            break
        try:
            text = fp.read_text(encoding="utf-8")
        except OSError:
            continue
        chunk = text[:max_per_file]
        if len(text) > len(chunk):
            chunk += "\n... (truncated)"
        lines.append(f"### {fp.name}")
        lines.append("```python")
        lines.append(chunk.rstrip())
        lines.append("```")
        used += len(chunk)
    lines.append("</b9-workspace-files>")
    return "\n".join(lines) if used else ""


def prepare_b9_subagent_workspace(
    workspace: Path,
    *,
    session_key: str,
) -> str:
    """Seed read_state + return context preamble for B9 delegate."""
    seed_b9_workspace_read_state(workspace, session_key=session_key)
    return build_b9_workspace_preamble(workspace)


def format_oracle_replay_block(task_id: str) -> str:
    """Mandatory oracle gold steps for retry after no_edit / wrong_patch."""
    from butler.dev_engine.b9_oracle_curriculum import get_episode

    ep = get_episode(task_id)
    if ep is None:
        return ""
    lines = [
        "## ORACLE REPLAY (mandatory)",
        f"Task {ep.task_id}: {ep.title}",
        f"pattern: {ep.pattern_summary}",
        "Execute these steps in order:",
    ]
    for step in ep.steps:
        tool = step.action
        if tool == "terminal" and step.target == "pytest":
            tool = "run_pytest"
            target = "test_b9.py"
        else:
            target = step.target
        lines.append(f"- {tool} `{target}`: {step.detail}")
    if task_id == "B9L_test_driven_add":
        lines.extend([
            "",
            "write_file template for service.py:",
            "```python",
            "def ping():",
            "    return 'pong'",
            "```",
        ])
    return "\n".join(lines)


def build_b9_wrong_patch_retry_banner(failure_tail: str) -> str:
    extra = ""
    try:
        from butler.dev_engine.b9_live_tuning import build_b9_verify_hint

        hint = build_b9_verify_hint(failure_tail)
        if hint:
            extra = f"\nHint: {hint}\n"
    except Exception:
        pass
    return (
        "## WRONG-PATCH RETRY (mandatory)\n"
        "Previous edit did not make pytest pass. Follow ORACLE REPLAY steps; "
        "fix implementation (not test_b9.py) and run run_pytest until green."
        f"{extra}"
    )


__all__ = [
    "apply_b9_pytest_success_gate",
    "build_b9_wrong_patch_retry_banner",
    "build_b9_workspace_preamble",
    "format_oracle_replay_block",
    "is_b9_benchmark_category",
    "prepare_b9_subagent_workspace",
    "resolve_b9_workspace",
    "seed_b9_workspace_read_state",
]
