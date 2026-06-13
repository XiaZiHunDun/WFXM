"""B9 delegate harness gates — pytest success, workspace pre-read, oracle replay."""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable, Iterator

from butler.dev_engine.b9_live_tuning import B9_LIVE_CATEGORY

SWE_LIVE_CATEGORY = "swe-benchmark"
LINGWEN_DRILL_CATEGORY = "lingwen-drill"
LINGWEN_PROD_SAMPLE_CATEGORY = "lingwen-prod-sample"
BENCHMARK_CATEGORIES: frozenset[str] = frozenset(
    {B9_LIVE_CATEGORY, SWE_LIVE_CATEGORY, LINGWEN_DRILL_CATEGORY, LINGWEN_PROD_SAMPLE_CATEGORY}
)

_B9_PREAMBLE_MAX_BYTES = 12_000
_B9_PREAMBLE_PER_FILE = 4_000
_BENCHMARK_VERIFY: ContextVar[Callable[[Path], tuple[bool, str]] | None] = ContextVar(
    "benchmark_verify",
    default=None,
)


def is_b9_benchmark_category(
    category: str = "",
    category_meta: dict[str, Any] | None = None,
) -> bool:
    cat = str(category or (category_meta or {}).get("category") or "").strip()
    return cat == B9_LIVE_CATEGORY


def is_benchmark_category(
    category: str = "",
    category_meta: dict[str, Any] | None = None,
) -> bool:
    cat = str(category or (category_meta or {}).get("category") or "").strip()
    return cat in BENCHMARK_CATEGORIES


@contextmanager
def benchmark_verify_context(
    verify_fn: Callable[[Path], tuple[bool, str]],
) -> Iterator[None]:
    """Thread delegate success gate to task-specific verify (e.g. SWE instances)."""
    token = _BENCHMARK_VERIFY.set(verify_fn)
    try:
        yield
    finally:
        _BENCHMARK_VERIFY.reset(token)


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
    if not is_benchmark_category(category, category_meta):
        return True, out
    ws = resolve_b9_workspace(project)
    if ws is None:
        msg = "BENCHMARK_PYTEST_GATE: workspace unresolved"
        if msg not in out:
            out.append(msg)
        return False, out
    hook = _BENCHMARK_VERIFY.get()
    if hook is not None:
        ok, tail = hook(ws)
    elif is_b9_benchmark_category(category, category_meta):
        from butler.dev_engine.b9_verify_utils import pytest_verify

        ok, tail = pytest_verify(ws)
    else:
        return True, out
    if ok:
        return True, out
    hint = ""
    try:
        from butler.dev_engine.b9_live_tuning import build_b9_verify_hint

        hint = build_b9_verify_hint(tail)
    except Exception:
        pass
    msg = f"BENCHMARK_PYTEST_GATE: verify not green — {(tail or 'failed')[:360]}"
    if hint:
        msg = f"{msg} | hint: {hint}"
    if msg not in out:
        out.append(msg)
    return False, out


def _iter_workspace_py_files(
    workspace: Path,
    *,
    max_depth: int = 2,
    max_files: int = 24,
) -> list[Path]:
    ws = workspace.resolve()
    found: list[Path] = []
    for depth in range(max_depth + 1):
        pattern = "/".join(["*"] * depth) + ("/*.py" if depth else "*.py")
        for fp in sorted(ws.glob(pattern)):
            if fp.is_file() and fp.suffix == ".py" and fp.name != "_swe_test.py":
                found.append(fp)
        if len(found) >= max_files:
            break
    # de-dup while preserving order
    seen: set[Path] = set()
    unique: list[Path] = []
    for fp in found:
        key = fp.resolve()
        if key in seen:
            continue
        seen.add(key)
        unique.append(fp)
        if len(unique) >= max_files:
            break
    return unique


def seed_b9_workspace_read_state(
    workspace: Path,
    *,
    session_key: str,
    max_depth: int = 1,
) -> int:
    """Pre-record read_file state for workspace .py files (READ_STATE relief)."""
    from butler.core.read_state import record_read_state

    ws = workspace.resolve()
    if not ws.is_dir():
        return 0
    count = 0
    paths = _iter_workspace_py_files(ws, max_depth=max_depth)
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
    max_depth: int = 1,
) -> str:
    """Inject workspace source snapshot so delegate can patch without READ_STATE friction."""
    ws = workspace.resolve()
    if not ws.is_dir():
        return ""
    lines = [
        "<benchmark-workspace-files>",
        "Pre-loaded workspace sources (also seeded in read_state — patch/write allowed):",
    ]
    used = 0
    for fp in _iter_workspace_py_files(ws, max_depth=max_depth):
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
        rel = fp.relative_to(ws) if fp.is_relative_to(ws) else fp.name
        lines.append(f"### {rel}")
        lines.append("```python")
        lines.append(chunk.rstrip())
        lines.append("```")
        used += len(chunk)
    lines.append("</benchmark-workspace-files>")
    return "\n".join(lines) if used else ""


def prepare_b9_subagent_workspace(
    workspace: Path,
    *,
    session_key: str,
    max_depth: int = 1,
) -> str:
    """Seed read_state + return context preamble for benchmark delegate."""
    seed_b9_workspace_read_state(workspace, session_key=session_key, max_depth=max_depth)
    return build_b9_workspace_preamble(workspace, max_depth=max_depth)


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


def dev_verify_success_gate_enabled() -> bool:
    raw = os.getenv("BUTLER_DEV_VERIFY_SUCCESS_GATE", "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def apply_dev_auto_verify_success_gate(
    *,
    role: str = "",
    base_success: bool,
    issues: list[str] | None = None,
    dev_engine: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """Production dev: edits without green verify must not count as delegate success."""
    out = list(issues or [])
    if not base_success:
        return False, out
    norm = str(role or "").replace("_agent", "").strip().lower()
    if norm != "dev":
        return True, out
    if not dev_verify_success_gate_enabled():
        return True, out
    try:
        from butler.dev_engine.dev_tools import auto_verify_enabled

        if not auto_verify_enabled():
            return True, out
    except Exception:
        return True, out

    de = dev_engine if isinstance(dev_engine, dict) else {}
    edits = int(de.get("edits") or 0)
    if edits <= 0:
        return True, out
    if de.get("verify_passed") is True:
        return True, out
    if de.get("verify_passed") is not False:
        return True, out

    tail = str(de.get("verify_output_tail") or "")
    hint = ""
    try:
        from butler.dev_engine.b9_live_tuning import build_b9_verify_hint

        hint = build_b9_verify_hint(tail)
    except Exception:
        pass
    msg = "DEV_VERIFY_GATE: 有编辑但自动验证未通过"
    if hint:
        msg += f" | hint: {hint}"
    if msg not in out:
        out.append(msg)
    return False, out


def coding_strict_pilot_categories() -> frozenset[str]:
    try:
        from butler.dev_engine.prod_delegate_bridge import PROD_PLAYBOOK_CATEGORIES

        return PROD_PLAYBOOK_CATEGORIES
    except Exception:
        return frozenset({"deep", "quick", "nexus-sprint"})


def apply_coding_strict_pilot_gate(
    *,
    category: str = "",
    category_meta: dict[str, Any] | None = None,
    role: str = "",
    base_success: bool,
    issues: list[str] | None = None,
    dev_engine: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """CA4 pilot: strict mode blocks dev delegate when theorem violations remain."""
    out = list(issues or [])
    if not base_success:
        return False, out
    try:
        from butler.dev_engine.dev_tools import coding_strict_enabled

        if not coding_strict_enabled():
            return True, out
    except Exception:
        return True, out

    norm = str(role or "").replace("_agent", "").strip().lower()
    if norm != "dev":
        return True, out

    cat = str(category or (category_meta or {}).get("category") or "").strip()
    pilot = coding_strict_pilot_categories()
    if cat and cat not in pilot:
        return True, out

    de = dev_engine if isinstance(dev_engine, dict) else {}
    ck = de.get("coding_knowledge") if isinstance(de.get("coding_knowledge"), dict) else {}
    violated = ck.get("violated") or ck.get("violated_theorems") or []
    if not violated:
        return True, out

    ids = [str(v) for v in violated if v]
    msg = f"CODING_STRICT_GATE: theorem violations remain ({', '.join(ids[:5])})"
    if msg not in out:
        out.append(msg)
    return False, out


__all__ = [
    "BENCHMARK_CATEGORIES",
    "SWE_LIVE_CATEGORY",
    "apply_b9_pytest_success_gate",
    "apply_coding_strict_pilot_gate",
    "apply_dev_auto_verify_success_gate",
    "benchmark_verify_context",
    "build_b9_wrong_patch_retry_banner",
    "build_b9_workspace_preamble",
    "dev_verify_success_gate_enabled",
    "format_oracle_replay_block",
    "is_b9_benchmark_category",
    "is_benchmark_category",
    "prepare_b9_subagent_workspace",
    "resolve_b9_workspace",
    "seed_b9_workspace_read_state",
]
