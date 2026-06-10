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
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class B9Mode(str, Enum):
    ORACLE = "oracle"
    LIVE = "live"


@dataclass
class B9TaskSpec:
    task_id: str
    description: str
    delegate_prompt: str
    setup: Callable[[Path], None]
    verify: Callable[[Path], tuple[bool, str]]
    oracle_apply: Callable[[Path], None]


@dataclass
class B9Result:
    task_id: str
    description: str
    passed: bool
    mode: str
    score: float = 0.0
    failure_reasons: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "passed": self.passed,
            "mode": self.mode,
            "score": self.score,
            "failure_reasons": self.failure_reasons,
            "tools_used": self.tools_used,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }


@dataclass
class B9Report:
    results: list[B9Result] = field(default_factory=list)
    mode: str = B9Mode.ORACLE.value

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


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
]


def resolve_b9_mode() -> B9Mode:
    if os.getenv("BUTLER_EVAL_LLM_BENCHMARK", "0").strip() in ("1", "true", "yes"):
        return B9Mode.LIVE
    return B9Mode.ORACLE


def _run_live_delegate(
    workspace: Path,
    spec: B9TaskSpec,
) -> tuple[bool, list[str], list[str]]:
    """Run delegate_task with real LLM. Returns (ok, tools_used, errors)."""
    errors: list[str] = []
    tools_used: list[str] = []
    try:
        from butler.execution_context import use_execution_context
        from butler.orchestrator import ButlerOrchestrator
        from butler.tools.registry import dispatch_tool

        orch = ButlerOrchestrator(user_id="b9-benchmark", channel="cli")
        session_key = "b9:benchmark"
        with use_execution_context(orch, session_key=session_key):
            monkeypatch_root = os.environ.get("BUTLER_TOOL_SAFE_ROOT", "")
            os.environ["BUTLER_TOOL_SAFE_ROOT"] = str(workspace.resolve())
            try:
                raw = dispatch_tool(
                    "delegate_task",
                    {
                        "role": "dev",
                        "task": spec.delegate_prompt,
                        "context": f"workspace={workspace}",
                    },
                )
            finally:
                if monkeypatch_root:
                    os.environ["BUTLER_TOOL_SAFE_ROOT"] = monkeypatch_root
        data = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("{") else {}
        if isinstance(data, dict):
            tools_used = list(data.get("tools_used") or [])
            if not data.get("success", True) and data.get("error"):
                errors.append(str(data["error"]))
    except Exception as exc:
        errors.append(str(exc))
        return False, tools_used, errors

    ok, msg = spec.verify(workspace)
    if not ok:
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
            result.passed = ok
        else:
            spec.oracle_apply(workspace)
            ok, msg = spec.verify(workspace)
            result.passed = ok
            if not ok:
                result.failure_reasons.append(msg)
            result.tools_used = ["oracle_apply"]
        result.score = 1.0 if result.passed else 0.0
    except Exception as exc:
        result.failure_reasons.append(str(exc))
    result.elapsed_seconds = time.time() - t0
    return result


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
    "B9_TASKS",
    "resolve_b9_mode",
    "run_b9_task",
    "run_llm_delegate_benchmarks",
]
