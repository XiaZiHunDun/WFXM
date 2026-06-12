"""B9 — LLM delegate end-to-end benchmarks (O9).

Unlike B1–B8 (oracle edits), B9 exercises the delegate fix path and scores
structural verification. Two modes:

- **oracle** (default, CI): apply known patch — validates task specs + verify hooks.
- **live** (``BUTLER_EVAL_LLM_BENCHMARK=1``): run ``delegate_task`` with real LLM.

Scores integrate with ``eval_bridge`` / LangFuse via ``llm_benchmark_to_scores``.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from butler.dev_engine.b9_types import B9Mode, B9Report, B9Result, B9TaskSpec

logger = logging.getLogger(__name__)


def _setup_b9_fix_greet(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "hello.py").write_text(
        "def greet():\n    return 'hi'\n",
        encoding="utf-8",
    )


def _oracle_b9_fix_greet(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_patch

    _rec, err = apply_patch(ws / "hello.py", "return 'hi'", "return 'hello'")
    if err:
        raise RuntimeError(err)


def _verify_b9_fix_greet(ws: Path) -> tuple[bool, str]:
    path = ws / "hello.py"
    if not path.is_file():
        return False, "hello.py missing"
    text = path.read_text(encoding="utf-8")
    if "return 'hello'" not in text:
        return False, f"expected return 'hello', got: {text[:80]}"
    return True, "greet returns hello"


def _setup_b9_create_marker(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)


def _oracle_b9_create_marker(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_write

    _rec, err = apply_write(ws / "b9_marker.txt", "b9-ok\n")
    if err:
        raise RuntimeError(err)


def _verify_b9_create_marker(ws: Path) -> tuple[bool, str]:
    path = ws / "b9_marker.txt"
    if not path.is_file():
        return False, "b9_marker.txt missing"
    if path.read_text(encoding="utf-8").strip() != "b9-ok":
        return False, "marker content mismatch"
    return True, "marker created"


def _setup_b9_fix_syntax(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "calc.py").write_text(
        "def add(a, b)\n    return a + b\n",
        encoding="utf-8",
    )


def _oracle_b9_fix_syntax(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_patch

    _rec, err = apply_patch(ws / "calc.py", "def add(a, b)\n", "def add(a, b):\n")
    if err:
        raise RuntimeError(err)


def _verify_b9_fix_syntax(ws: Path) -> tuple[bool, str]:
    path = ws / "calc.py"
    if not path.is_file():
        return False, "calc.py missing"
    if "def add(a, b):" not in path.read_text(encoding="utf-8"):
        return False, "missing colon after function signature"
    return True, "syntax fixed"


def _setup_b9_add_fibonacci(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)


def _oracle_b9_add_fibonacci(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_write

    content = (
        "def fibonacci(n: int) -> int:\n"
        "    if n <= 1:\n"
        "        return n\n"
        "    return fibonacci(n - 1) + fibonacci(n - 2)\n"
    )
    _rec, err = apply_write(ws / "fib.py", content)
    if err:
        raise RuntimeError(err)


def _verify_b9_add_fibonacci(ws: Path) -> tuple[bool, str]:
    path = ws / "fib.py"
    if not path.is_file():
        return False, "fib.py missing"
    if "def fibonacci" not in path.read_text(encoding="utf-8"):
        return False, "fibonacci function missing"
    return True, "fibonacci added"


def _setup_b9_fix_off_by_one(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "math_utils.py").write_text(
        "def range_sum(n):\n    return sum(range(n))\n",
        encoding="utf-8",
    )


def _oracle_b9_fix_off_by_one(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_patch

    _rec, err = apply_patch(ws / "math_utils.py", "range(n)", "range(n + 1)")
    if err:
        raise RuntimeError(err)


def _verify_b9_fix_off_by_one(ws: Path) -> tuple[bool, str]:
    path = ws / "math_utils.py"
    if not path.is_file():
        return False, "math_utils.py missing"
    if "range(n + 1)" not in path.read_text(encoding="utf-8"):
        return False, "off-by-one not fixed"
    return True, "range_sum fixed"


def _setup_b9_fix_add_negative(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "calc.py").write_text(
        "def add(a, b):\n    if a < 0 or b < 0:\n        return 0\n    return a + b\n",
        encoding="utf-8",
    )


def _oracle_b9_fix_add_negative(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_patch

    old = "    if a < 0 or b < 0:\n        return 0\n"
    _rec, err = apply_patch(ws / "calc.py", old, "")
    if err:
        raise RuntimeError(err)


def _verify_b9_fix_add_negative(ws: Path) -> tuple[bool, str]:
    path = ws / "calc.py"
    if not path.is_file():
        return False, "calc.py missing"
    text = path.read_text(encoding="utf-8")
    if "return 0" in text:
        return False, "still returns 0 for negatives"
    if "return a + b" not in text:
        return False, "missing add return"
    return True, "add handles negatives"


def _setup_b9_write_readme(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)


def _oracle_b9_write_readme(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_write

    _rec, err = apply_write(ws / "README.md", "# B9 benchmark\n")
    if err:
        raise RuntimeError(err)


def _verify_b9_write_readme(ws: Path) -> tuple[bool, str]:
    path = ws / "README.md"
    if not path.is_file():
        return False, "README.md missing"
    if "# B9" not in path.read_text(encoding="utf-8"):
        return False, "README missing # B9 heading"
    return True, "readme created"


def _setup_b9_rename_method(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "api.py").write_text(
        "class Client:\n    def getData(self):\n        return {}\n",
        encoding="utf-8",
    )


def _oracle_b9_rename_method(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_patch

    _rec, err = apply_patch(ws / "api.py", "getData", "get_data")
    if err:
        raise RuntimeError(err)


def _verify_b9_rename_method(ws: Path) -> tuple[bool, str]:
    path = ws / "api.py"
    if not path.is_file():
        return False, "api.py missing"
    text = path.read_text(encoding="utf-8")
    if "def get_data" not in text:
        return False, "get_data not found"
    if "getData" in text:
        return False, "getData still present"
    return True, "method renamed"


B9_TASKS: list[B9TaskSpec] = [
    B9TaskSpec(
        task_id="B9_fix_greet",
        description="Delegate dev: fix hello.py return value",
        delegate_prompt=(
            "Fix hello.py so greet() returns 'hello' instead of 'hi'. "
            "Only modify hello.py."
        ),
        setup=_setup_b9_fix_greet,
        verify=_verify_b9_fix_greet,
        oracle_apply=_oracle_b9_fix_greet,
    ),
    B9TaskSpec(
        task_id="B9_create_marker",
        description="Delegate dev: create b9_marker.txt",
        delegate_prompt="Create b9_marker.txt with exactly one line: b9-ok",
        setup=_setup_b9_create_marker,
        verify=_verify_b9_create_marker,
        oracle_apply=_oracle_b9_create_marker,
    ),
    B9TaskSpec(
        task_id="B9_fix_syntax",
        description="Delegate dev: fix missing colon in calc.py",
        delegate_prompt=(
            "Fix the syntax error in calc.py (add missing colon after function signature). "
            "Only modify calc.py."
        ),
        setup=_setup_b9_fix_syntax,
        verify=_verify_b9_fix_syntax,
        oracle_apply=_oracle_b9_fix_syntax,
    ),
    B9TaskSpec(
        task_id="B9_add_fibonacci",
        description="Delegate dev: add fibonacci function to fib.py",
        delegate_prompt=(
            "Create fib.py with a recursive fibonacci(n) function. "
            "Only create or edit fib.py."
        ),
        setup=_setup_b9_add_fibonacci,
        verify=_verify_b9_add_fibonacci,
        oracle_apply=_oracle_b9_add_fibonacci,
    ),
    B9TaskSpec(
        task_id="B9_fix_off_by_one",
        description="Delegate dev: fix off-by-one in range_sum",
        delegate_prompt=(
            "Fix range_sum in math_utils.py so range_sum(3) includes 3. "
            "Only modify math_utils.py."
        ),
        setup=_setup_b9_fix_off_by_one,
        verify=_verify_b9_fix_off_by_one,
        oracle_apply=_oracle_b9_fix_off_by_one,
    ),
    B9TaskSpec(
        task_id="B9_fix_add_negative",
        description="Delegate dev: fix add() to handle negative numbers",
        delegate_prompt=(
            "Fix add() in calc.py so negative inputs sum correctly (remove early return 0). "
            "Only modify calc.py."
        ),
        setup=_setup_b9_fix_add_negative,
        verify=_verify_b9_fix_add_negative,
        oracle_apply=_oracle_b9_fix_add_negative,
    ),
    B9TaskSpec(
        task_id="B9_write_readme",
        description="Delegate dev: create README.md with heading",
        delegate_prompt="Create README.md with first line exactly: # B9 benchmark",
        setup=_setup_b9_write_readme,
        verify=_verify_b9_write_readme,
        oracle_apply=_oracle_b9_write_readme,
    ),
    B9TaskSpec(
        task_id="B9_rename_method",
        description="Delegate dev: rename getData to get_data in api.py",
        delegate_prompt=(
            "Rename method getData to get_data in api.py. Only modify api.py."
        ),
        setup=_setup_b9_rename_method,
        verify=_verify_b9_rename_method,
        oracle_apply=_oracle_b9_rename_method,
    ),
]

from butler.dev_engine.b9_live_fixed_tasks import (  # noqa: E402
    B9_LIVE_FIXED_TASKS,
    B9_LIVE_FIXED_TASK_IDS,
)

B9_TASKS.extend(B9_LIVE_FIXED_TASKS)


def resolve_b9_mode() -> B9Mode:
    if os.getenv("BUTLER_EVAL_LLM_BENCHMARK", "0").strip() in ("1", "true", "yes"):
        return B9Mode.LIVE
    return B9Mode.ORACLE


_B9_LIVE_PROJECT_NAME = "__b9_live_benchmark__"


def _bind_b9_live_project(workspace: Path, orch: Any, *, session_key: str) -> None:
    """Register ephemeral project + bind session so delegate resolves workspace."""
    from butler.project.model import Project

    ws = workspace.resolve()
    pm = orch.project_manager
    pm._projects[_B9_LIVE_PROJECT_NAME] = Project(
        name=_B9_LIVE_PROJECT_NAME,
        type="software",
        description="B9 LIVE benchmark ephemeral project",
        workspace=ws,
    )
    parts = str(session_key or "b9:benchmark").split(":", 1)
    platform = parts[0] or "b9"
    chat_id = parts[1] if len(parts) > 1 else "benchmark"
    pm.switch_project_for_chat(platform=platform, chat_id=chat_id, name=_B9_LIVE_PROJECT_NAME)
    # Child delegate loops use child_session_key; global fallback ensures permissions resolve workspace.
    pm.switch_project(_B9_LIVE_PROJECT_NAME)


def _run_live_delegate(
    workspace: Path,
    spec: B9TaskSpec,
) -> tuple[bool, list[str], list[str]]:
    """Run delegate_task with real LLM. Returns (ok, tools_used, errors)."""
    from contextlib import nullcontext

    from butler.dev_engine.b9_delegate_gate import (
        build_b9_wrong_patch_retry_banner,
        format_oracle_replay_block,
    )
    from butler.dev_engine.b9_live_tuning import (
        b9_has_edit_tools,
        b9_live_runtime_env,
        b9_live_tuning_patch,
        build_b9_delegate_args,
        build_b9_no_edit_retry_banner,
    )

    _B9_LIVE_MAX_ATTEMPTS = 3
    from butler.ops.eval_config_overrides import temporary_overrides

    errors: list[str] = []
    tools_used: list[str] = []
    tuning_patch = b9_live_tuning_patch()
    override_ctx = (
        temporary_overrides(tuning_patch) if tuning_patch else nullcontext()
    )
    delegate_args = build_b9_delegate_args(spec, workspace.resolve())
    from butler.dev_engine.b9_delegate_gate import benchmark_verify_context

    try:
        from butler.execution_context import use_execution_context
        from butler.orchestrator import ButlerOrchestrator
        from butler.tools.registry import dispatch_tool

        orch = ButlerOrchestrator(user_id="b9-benchmark", channel="cli")
        session_key = "b9:benchmark"
        ws = workspace.resolve()
        with (
            override_ctx,
            b9_live_runtime_env(),
            benchmark_verify_context(spec.verify),
            use_execution_context(orch, session_key=session_key),
        ):
            _bind_b9_live_project(ws, orch, session_key=session_key)
            monkeypatch_root = os.environ.get("BUTLER_TOOL_SAFE_ROOT", "")
            os.environ["BUTLER_TOOL_SAFE_ROOT"] = str(ws)
            try:
                failure_tail = ""
                base_context = delegate_args["context"]
                for attempt in range(_B9_LIVE_MAX_ATTEMPTS):
                    if attempt == 0:
                        args = delegate_args
                    else:
                        replay = (
                            format_oracle_replay_block(spec.task_id)
                            if spec.task_id.startswith("B9L_")
                            else ""
                        )
                        if not b9_has_edit_tools(tools_used):
                            banner = build_b9_no_edit_retry_banner(
                                base_context,
                                failure_tail=failure_tail,
                            )
                        else:
                            banner = build_b9_wrong_patch_retry_banner(failure_tail)
                        extra = "\n\n".join(x for x in (replay, banner) if x)
                        args = {
                            **delegate_args,
                            "context": f"{extra}\n\n{base_context}",
                        }
                    raw = dispatch_tool("delegate_task", args)
                    data = (
                        json.loads(raw)
                        if isinstance(raw, str) and raw.strip().startswith("{")
                        else {}
                    )
                    if isinstance(data, dict):
                        for name in data.get("tools_used") or []:
                            if name and name not in tools_used:
                                tools_used.append(str(name))
                        if not data.get("success", True) and data.get("error"):
                            errors.append(str(data["error"]))
                    verify_ok, verify_msg = spec.verify(ws)
                    if verify_ok:
                        errors.clear()
                        break
                    failure_tail = verify_msg or ""
                    if errors:
                        failure_tail = f"{failure_tail}\n{errors[-1]}"
                    if attempt >= _B9_LIVE_MAX_ATTEMPTS - 1:
                        if verify_msg:
                            errors.append(verify_msg)
                        break
            finally:
                if monkeypatch_root:
                    os.environ["BUTLER_TOOL_SAFE_ROOT"] = monkeypatch_root
                elif "BUTLER_TOOL_SAFE_ROOT" in os.environ:
                    del os.environ["BUTLER_TOOL_SAFE_ROOT"]
    except Exception as exc:
        errors.append(str(exc))
        return False, tools_used, errors

    ok, msg = spec.verify(workspace)
    if not ok and msg and msg not in errors:
        errors.append(msg)
    return ok and not errors, tools_used, errors


def run_b9_task(
    spec: B9TaskSpec,
    workspace: Path,
    *,
    mode: B9Mode | None = None,
) -> B9Result:
    mode = mode or resolve_b9_mode()
    t0 = time.time()
    result = B9Result(
        task_id=spec.task_id,
        description=spec.description,
        passed=False,
        mode=mode.value,
    )
    try:
        spec.setup(workspace)
        if mode == B9Mode.LIVE:
            ok, tools, errs = _run_live_delegate(workspace, spec)
            result.tools_used = tools
            result.failure_reasons = errs
            verify_ok, verify_msg = spec.verify(workspace)
            if spec.expect_pass:
                result.passed = ok and verify_ok
                if not verify_ok and verify_msg:
                    result.failure_reasons.append(verify_msg)
            else:
                result.passed = not verify_ok
                if verify_ok:
                    result.failure_reasons.append(
                        verify_msg or "expected unfixed workspace but verify passed"
                    )
        else:
            if spec.expect_pass:
                spec.oracle_apply(workspace)
            ok, msg = spec.verify(workspace)
            result.passed = ok if spec.expect_pass else (not ok)
            if spec.expect_pass and not ok:
                result.failure_reasons.append(msg)
            elif not spec.expect_pass and ok:
                result.failure_reasons.append(msg or "expected verify fail for STUCK task")
            result.tools_used = ["oracle_apply"] if spec.expect_pass else ["noop"]
        result.score = 1.0 if result.passed else 0.0
    except Exception as exc:
        result.failure_reasons.append(str(exc))
    result.elapsed_seconds = time.time() - t0
    try:
        from butler.ops.b9_lessons import record_b9_run_lesson

        record_b9_run_lesson(result, spec)
    except Exception:
        pass
    return result


def run_b9_live_fixed_benchmarks(
    workspace: Path | None = None,
    *,
    mode: B9Mode | None = None,
) -> B9Report:
    """Run the 10-task LIVE fixed set (weekly LLM gate)."""
    return run_llm_delegate_benchmarks(
        workspace,
        mode=mode,
        tasks=B9_LIVE_FIXED_TASKS,
    )


def run_llm_delegate_benchmarks(
    workspace: Path | None = None,
    *,
    mode: B9Mode | None = None,
    tasks: list[B9TaskSpec] | None = None,
) -> B9Report:
    import tempfile

    mode = mode or resolve_b9_mode()
    report = B9Report(mode=mode.value)
    task_list = tasks or B9_TASKS

    for spec in task_list:
        if workspace:
            ws = workspace / spec.task_id
            ws.mkdir(parents=True, exist_ok=True)
        else:
            ws = Path(tempfile.mkdtemp(prefix=f"b9_{spec.task_id}_"))
        report.results.append(run_b9_task(spec, ws, mode=mode))

    return report


__all__ = [
    "B9Mode",
    "B9Report",
    "B9Result",
    "B9TaskSpec",
    "B9_LIVE_FIXED_TASK_IDS",
    "B9_LIVE_FIXED_TASKS",
    "B9_TASKS",
    "resolve_b9_mode",
    "run_b9_live_fixed_benchmarks",
    "run_b9_task",
    "run_llm_delegate_benchmarks",
]
