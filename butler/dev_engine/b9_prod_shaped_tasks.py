"""B9 tasks modeled on production failure taxonomy (phase 2 replay).

Maps LangFuse annotation categories to reproducible oracle benchmarks:
  - verify_fail  → B9L_prod_verify_fail
  - patch_wrong  → B9L_prod_patch_wrong
  - no_test      → B9L_prod_no_test

When ``delegate_failures.jsonl`` has real cases, use ``delegate_failure_b9_promote``
to enqueue and scaffold; these tasks serve as golden templates until then.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from butler.dev_engine.b9_task_fixtures import (
    _oracle_b9l_cross_module_rename,
    _oracle_b9l_multi_file_import,
    _setup_b9l_cross_module_rename,
    _setup_b9l_multi_file_import,
    _verify_b9l_cross_module_rename,
    _verify_b9l_multi_file_import,
)
from butler.dev_engine.b9_types import B9TaskSpec
from butler.dev_engine.b9_verify_utils import pytest_verify as _pytest_verify
from butler.dev_engine.edit_ops import apply_write
from butler.dev_engine.edit_ops import apply_patch


def _verify_ws(ws: Path) -> tuple[bool, str]:
    return cast(tuple[bool, str], _pytest_verify(ws))


def _setup_b9l_prod_verify_fail(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "divider.py").write_text(
        "def divide(a, b):\n    return a / b\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from divider import divide\n\n\ndef test_divide_zero():\n"
        "    assert divide(1, 0) == 0\n",
        encoding="utf-8",
    )


def _oracle_b9l_prod_verify_fail(ws: Path) -> None:

    content = (
        "def divide(a, b):\n"
        "    if b == 0:\n"
        "        return 0\n"
        "    return a / b\n"
    )
    _rec, err = apply_write(ws / "divider.py", content)
    if err:
        raise RuntimeError(err)


def _verify_b9l_prod_verify_fail(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


def _setup_b9l_prod_patch_wrong(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "logic.py").write_text(
        "def clamp(x, upper):\n    return x if x < upper else upper\n",
        encoding="utf-8",
    )
    (ws / "decoy.py").write_text(
        "# unrelated helper — do not edit for this task\n"
        "def noop():\n    return None\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from logic import clamp\n\n\ndef test_clamp_inclusive():\n"
        "    assert clamp(5, 5) == 5\n",
        encoding="utf-8",
    )


def _oracle_b9l_prod_patch_wrong(ws: Path) -> None:

    _rec, err = apply_patch(
        ws / "logic.py",
        "return x if x < upper else upper",
        "return x if x <= upper else upper",
    )
    if err:
        raise RuntimeError(err)


def _verify_b9l_prod_patch_wrong(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


def _setup_b9l_prod_no_test(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "formatter.py").write_text(
        "def label(name):\n    return f'  {name}  '\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from formatter import label\n\n\ndef test_label_trimmed():\n"
        "    assert label('ok') == 'ok'\n",
        encoding="utf-8",
    )


def _oracle_b9l_prod_no_test(ws: Path) -> None:

    _rec, err = apply_patch(
        ws / "formatter.py",
        "return f'  {name}  '",
        "return f'  {name}  '.strip()",
    )
    if err:
        raise RuntimeError(err)


def _verify_b9l_prod_no_test(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


def _setup_b9l_prod_demo_fix_greet_return(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "greet.py").write_text(
        "def greet():\n    return 'hi'\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from greet import greet\n\n\ndef test_greet_returns_hello():\n"
        "    assert greet() == 'hello'\n",
        encoding="utf-8",
    )


def _oracle_b9l_prod_demo_fix_greet_return(ws: Path) -> None:

    _rec, err = apply_patch(
        ws / "greet.py",
        "return 'hi'",
        "return 'hello'",
    )
    if err:
        raise RuntimeError(err)


def _verify_b9l_prod_demo_fix_greet_return(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


def _setup_b9l_prod_read_state_greet(ws: Path) -> None:
    _setup_b9l_prod_demo_fix_greet_return(ws)


def _oracle_b9l_prod_read_state_greet(ws: Path) -> None:
    _oracle_b9l_prod_demo_fix_greet_return(ws)


def _verify_b9l_prod_read_state_greet(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


def _setup_b9l_prod_main_helpers_import(ws: Path) -> None:
    _setup_b9l_multi_file_import(ws)


def _oracle_b9l_prod_main_helpers_import(ws: Path) -> None:
    _oracle_b9l_multi_file_import(ws)


def _verify_b9l_prod_main_helpers_import(ws: Path) -> tuple[bool, str]:
    return cast(tuple[bool, str], _verify_b9l_multi_file_import(ws))


def _setup_b9l_prod_cross_module_rename(ws: Path) -> None:
    _setup_b9l_cross_module_rename(ws)


def _oracle_b9l_prod_cross_module_rename(ws: Path) -> None:
    _oracle_b9l_cross_module_rename(ws)


def _verify_b9l_prod_cross_module_rename(ws: Path) -> tuple[bool, str]:
    return cast(tuple[bool, str], _verify_b9l_cross_module_rename(ws))


def _setup_b9l_prod_lingwen_demo_add(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    demo = ws / "demo"
    demo.mkdir(exist_ok=True)
    (demo / "__init__.py").write_text("", encoding="utf-8")
    (demo / "hello.py").write_text(
        '"""LingWen1 demo — add() bug for prod-shaped benchmark."""\n\n'
        "def greet(name: str) -> str:\n"
        '    return f"你好，{name}！"\n\n\n'
        "def add(a: float, b: float) -> float:\n"
        "    return a - b\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from demo.hello import add\n\n\ndef test_add_sum():\n"
        "    assert add(3.5, 4.5) == 8.0\n",
        encoding="utf-8",
    )


def _oracle_b9l_prod_lingwen_demo_add(ws: Path) -> None:

    _rec, err = apply_patch(
        ws / "demo" / "hello.py",
        "return a - b",
        "return a + b",
    )
    if err:
        raise RuntimeError(err)


def _verify_b9l_prod_lingwen_demo_add(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


def _setup_b9l_prod_lingwen_workflow_guard(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    scripts = ws / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    (scripts / "workflow_guard.py").write_text(
        '"""LingWen1 novel-factory/scripts — detect open completed batches."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n\n"
        "def has_open_completed(state: dict[str, Any]) -> bool:\n"
        '    """Return True when a completed batch still has open result text."""\n'
        '    completed = (state.get("review_queue") or {}).get("completed") or []\n'
        "    for entry in completed:\n"
        '        result = str(entry.get("result") or "")\n'
        '        if "待修复" in result or "未通过" in result:\n'
        "            return False\n"
        "    return False\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from scripts.workflow_guard import has_open_completed\n\n\n"
        "def test_open_batch_detected():\n"
        '    state = {"review_queue": {"completed": [{"batch_id": "b1", "result": "待修复 P0"}]}}\n'
        "    assert has_open_completed(state) is True\n",
        encoding="utf-8",
    )


def _oracle_b9l_prod_lingwen_workflow_guard(ws: Path) -> None:

    target = ws / "scripts" / "workflow_guard.py"
    _rec, err = apply_patch(
        target,
        '        if "待修复" in result or "未通过" in result:\n            return False',
        '        if "待修复" in result or "未通过" in result:\n            return True',
    )
    if err:
        raise RuntimeError(err)


def _verify_b9l_prod_lingwen_workflow_guard(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


def _setup_b9l_prod_lingwen_constants_docstring(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "constants.py").write_text("MAX_RETRIES = 3\n", encoding="utf-8")
    (ws / "test_b9.py").write_text(
        "import constants\n\n\ndef test_module_docstring_and_retries():\n"
        "    assert constants.__doc__ and constants.__doc__.strip()\n"
        "    assert constants.MAX_RETRIES == 3\n",
        encoding="utf-8",
    )


def _oracle_b9l_prod_lingwen_constants_docstring(ws: Path) -> None:

    content = (
        '"""LingWen1 project constants."""\n\n'
        "MAX_RETRIES = 3\n"
    )
    _rec, err = apply_write(ws / "constants.py", content)
    if err:
        raise RuntimeError(err)


def _verify_b9l_prod_lingwen_constants_docstring(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


_VALIDATE_PROGRESS_SCRIPT = '''#!/usr/bin/env python3
"""Minimal novel-factory progress validator for B9 prod-shaped benchmark."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "workflow_state.json"


def main() -> int:
    if not STATE_FILE.is_file():
        print(f"缺少 {STATE_FILE}", file=sys.stderr)
        return 1
    text = STATE_FILE.read_text(encoding="utf-8")
    if "OPEN_FIX" in text or "待修复" in text or "未通过" in text:
        print(f"错误: completed 批次 reviewer-batch-01 result 仍为未闭合: {text.strip()}")
        return 1
    if "PASSED" not in text and "已通过" not in text:
        print("错误: workflow_state 未标记已通过", file=sys.stderr)
        return 1
    print("进度验证: 通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _setup_b9l_prod_lingwen_validate_progress(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    nf = ws / "novel-factory"
    scripts = nf / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "validate_progress.py").write_text(_VALIDATE_PROGRESS_SCRIPT, encoding="utf-8")
    # Single-line state — minimal patch target for LIVE delegate.
    (nf / "workflow_state.json").write_text("status:OPEN_FIX\n", encoding="utf-8")
    (ws / "test_b9.py").write_text(
        "import subprocess\nimport sys\nfrom pathlib import Path\n\n\n"
        "def test_validate_progress_passes():\n"
        "    script = Path('novel-factory/scripts/validate_progress.py')\n"
        "    proc = subprocess.run(\n"
        "        [sys.executable, str(script)],\n"
        "        capture_output=True,\n"
        "        text=True,\n"
        "        cwd=Path('.'),\n"
        "        check=False,\n"
        "    )\n"
        "    assert proc.returncode == 0, proc.stdout + proc.stderr\n"
        "    assert '进度验证: 通过' in proc.stdout\n",
        encoding="utf-8",
    )


def _oracle_b9l_prod_lingwen_validate_progress(ws: Path) -> None:

    target = ws / "novel-factory" / "workflow_state.json"
    _rec, err = apply_patch(target, "status:OPEN_FIX", "status:PASSED")
    if err:
        raise RuntimeError(err)


def _verify_b9l_prod_lingwen_validate_progress(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


_READ_STATE_CONTEXT = (
    "## PRODUCTION LESSON (READ_STATE_REQUIRED)\n"
    "Previous delegate failed because patch/write ran before read_file.\n"
    "Mandatory: read_file greet.py AND test_b9.py first, then patch greet.py only."
)

_VALIDATE_PROGRESS_CONTEXT = (
    "## PRODUCTION LESSON (workflow_state unclosed batch)\n"
    "novel-factory/scripts/validate_progress.py exits 1 when "
    "workflow_state.json still contains OPEN_FIX.\n"
    "Mandatory steps:\n"
    "1. read_file novel-factory/workflow_state.json (one line: status:OPEN_FIX)\n"
    "2. patch novel-factory/workflow_state.json: old_string status:OPEN_FIX → "
    "new_string status:PASSED (copy exact text from read_file; patch only, not write_file)\n"
    "3. terminal: python3 novel-factory/scripts/validate_progress.py "
    "— stdout must include 进度验证: 通过\n"
    "Do not edit files under 06_意见仓库."
)

_BENCHMARK_READ_SPEC_CONTEXT = (
    "## PRODUCTION LESSON (b9-benchmark READ_STATE + no shell)\n"
    "Benchmark rules:\n"
    "1. read_file test_b9.py first — that is the acceptance spec\n"
    "2. read_file the implementation file before any patch\n"
    "3. patch only to fix greet.py; do NOT use terminal with shell metacharacters\n"
    "Previous failure: READ_STATE_REQUIRED and TOOL_ERROR from disallowed shell."
)


B9_PROD_SHAPED_TASKS: list[B9TaskSpec] = [
    B9TaskSpec(
        task_id="B9L_prod_verify_fail",
        description="Prod-shaped verify_fail: divide() must handle zero",
        delegate_prompt=(
            "Fix divider.py so test_b9.py passes. "
            "divide(1, 0) must return 0 without raising."
        ),
        setup=_setup_b9l_prod_verify_fail,
        verify=_verify_b9l_prod_verify_fail,
        oracle_apply=_oracle_b9l_prod_verify_fail,
        tags=("prod_shaped", "verify_fail", "pytest"),
    ),
    B9TaskSpec(
        task_id="B9L_prod_patch_wrong",
        description="Prod-shaped patch_wrong: fix logic.py not decoy.py",
        delegate_prompt=(
            "Fix clamp() in logic.py so test_b9.py passes (clamp(5, 5) should be 5). "
            "Do not edit decoy.py."
        ),
        setup=_setup_b9l_prod_patch_wrong,
        verify=_verify_b9l_prod_patch_wrong,
        oracle_apply=_oracle_b9l_prod_patch_wrong,
        tags=("prod_shaped", "patch_wrong", "pytest"),
    ),
    B9TaskSpec(
        task_id="B9L_prod_no_test",
        description="Prod-shaped no_test: trim label() whitespace",
        delegate_prompt=(
            "Fix formatter.py so label() returns trimmed text and test_b9.py passes."
        ),
        setup=_setup_b9l_prod_no_test,
        verify=_verify_b9l_prod_no_test,
        oracle_apply=_oracle_b9l_prod_no_test,
        tags=("prod_shaped", "no_test", "pytest"),
    ),
    B9TaskSpec(
        task_id="B9L_prod_demo_fix_greet_return",
        description="Prod-shaped verify_fail: greet() must return hello",
        delegate_prompt=(
            "Fix greet.py so greet() returns 'hello' instead of 'hi'. "
            "Only modify greet.py; test_b9.py must pass."
        ),
        setup=_setup_b9l_prod_demo_fix_greet_return,
        verify=_verify_b9l_prod_demo_fix_greet_return,
        oracle_apply=_oracle_b9l_prod_demo_fix_greet_return,
        tags=("prod_shaped", "verify_fail", "pytest", "promoted", "source:demo-fix-greet-return"),
    ),
    B9TaskSpec(
        task_id="B9L_prod_read_state_greet",
        description="Prod promoted: READ_STATE then fix greet() return",
        delegate_prompt=(
            "Fix greet.py so greet() returns 'hello' instead of 'hi'. "
            "You MUST read_file greet.py and test_b9.py before any patch. "
            "Only modify greet.py; test_b9.py must pass."
        ),
        setup=_setup_b9l_prod_read_state_greet,
        verify=_verify_b9l_prod_read_state_greet,
        oracle_apply=_oracle_b9l_prod_read_state_greet,
        benchmark_context_extra=_READ_STATE_CONTEXT,
        tags=("prod_shaped", "read_state", "verify_failed", "pytest", "promoted", "source:task_3a0bc9cf7f14"),
    ),
    B9TaskSpec(
        task_id="B9L_prod_main_helpers_import",
        description="Prod promoted: fix main.py import helpers module name",
        delegate_prompt=(
            "Fix main.py so it imports from helpers.py correctly. "
            "Tests in test_b9.py must pass. Only edit files in this workspace."
        ),
        setup=_setup_b9l_prod_main_helpers_import,
        verify=_verify_b9l_prod_main_helpers_import,
        oracle_apply=_oracle_b9l_prod_main_helpers_import,
        tags=("prod_shaped", "tool_wrong", "verify_failed", "pytest", "promoted", "source:task_12f8eb65e703"),
    ),
    B9TaskSpec(
        task_id="B9L_prod_cross_module_rename",
        description="Prod promoted: rename getData→get_data in pkg/client.py",
        delegate_prompt=(
            "Rename method getData to get_data in pkg/client.py and update pkg/__init__.py. "
            "test_b9.py must pass. read_file before patch."
        ),
        setup=_setup_b9l_prod_cross_module_rename,
        verify=_verify_b9l_prod_cross_module_rename,
        oracle_apply=_oracle_b9l_prod_cross_module_rename,
        tags=("prod_shaped", "multi_file", "refactor", "verify_failed", "pytest", "promoted", "source:task_1c1398702de8"),
    ),
    B9TaskSpec(
        task_id="B9L_prod_lingwen_demo_add",
        description="LingWen1 prod: fix demo/hello.py add() operator",
        delegate_prompt=(
            "Fix demo/hello.py in LingWen1 workspace: add(a, b) must return a + b. "
            "test_b9.py expects add(3.5, 4.5) == 8.0. Only edit demo/hello.py."
        ),
        setup=_setup_b9l_prod_lingwen_demo_add,
        verify=_verify_b9l_prod_lingwen_demo_add,
        oracle_apply=_oracle_b9l_prod_lingwen_demo_add,
        tags=("prod_shaped", "lingwen1", "verify_fail", "pytest", "promoted", "source:lingwen1-demo-add-fix"),
    ),
    B9TaskSpec(
        task_id="B9L_prod_lingwen_workflow_guard",
        description="LingWen1 prod: fix workflow_guard open-batch detection",
        delegate_prompt=(
            "Fix scripts/workflow_guard.py in LingWen1 novel-factory workspace: "
            "has_open_completed() must return True when completed batch result contains 待修复. "
            "test_b9.py must pass. Only edit scripts/workflow_guard.py."
        ),
        setup=_setup_b9l_prod_lingwen_workflow_guard,
        verify=_verify_b9l_prod_lingwen_workflow_guard,
        oracle_apply=_oracle_b9l_prod_lingwen_workflow_guard,
        tags=(
            "prod_shaped",
            "lingwen1",
            "novel_factory",
            "verify_fail",
            "pytest",
            "promoted",
            "source:lingwen1-workflow-guard-fix",
        ),
    ),
    B9TaskSpec(
        task_id="B9L_prod_lingwen_constants_docstring",
        description="LingWen1 prod: add module docstring to constants.py",
        delegate_prompt=(
            "Fix constants.py in LingWen1 workspace: add a one-line module docstring "
            "before MAX_RETRIES. MAX_RETRIES must stay 3. test_b9.py must pass. "
            "read_file constants.py before patch. No terminal."
        ),
        setup=_setup_b9l_prod_lingwen_constants_docstring,
        verify=_verify_b9l_prod_lingwen_constants_docstring,
        oracle_apply=_oracle_b9l_prod_lingwen_constants_docstring,
        tags=(
            "prod_shaped",
            "lingwen1",
            "verify_fail",
            "pytest",
            "promoted",
            "source:lingwen1-sample-constants-comment",
        ),
    ),
    B9TaskSpec(
        task_id="B9L_prod_lingwen_validate_progress",
        description="LingWen1 prod: fix workflow_state for validate_progress",
        delegate_prompt=(
            "Fix novel-factory/workflow_state.json so validate_progress passes. "
            "read_file first — file is exactly one line: status:OPEN_FIX. "
            "patch only: old_string status:OPEN_FIX → new_string status:PASSED. "
            "read_file again to confirm, then "
            "python3 novel-factory/scripts/validate_progress.py — expect 进度验证: 通过."
        ),
        setup=_setup_b9l_prod_lingwen_validate_progress,
        verify=_verify_b9l_prod_lingwen_validate_progress,
        oracle_apply=_oracle_b9l_prod_lingwen_validate_progress,
        benchmark_context_extra=_VALIDATE_PROGRESS_CONTEXT,
        tags=(
            "prod_shaped",
            "lingwen1",
            "novel_factory",
            "verify_fail",
            "pytest",
            "promoted",
            "source:lingwen1-sample-validate-progress",
        ),
    ),
    B9TaskSpec(
        task_id="B9L_prod_task_6d5304648da4",
        description="Prod promoted: b9-benchmark READ_STATE — read spec then patch greet",
        delegate_prompt=(
            "[category:b9-benchmark] Benchmark rules:\n"
            "1. read_file test_b9.py first — that is the acceptance spec\n"
            "2. read_file greet.py before any patch\n"
            "3. fix greet.py so greet() returns 'hello'; test_b9.py must pass. "
            "Do not use terminal with shell metacharacters."
        ),
        setup=_setup_b9l_prod_read_state_greet,
        verify=_verify_b9l_prod_read_state_greet,
        oracle_apply=_oracle_b9l_prod_read_state_greet,
        benchmark_context_extra=_BENCHMARK_READ_SPEC_CONTEXT,
        tags=(
            "prod_shaped",
            "read_state",
            "verify_fail",
            "pytest",
            "promoted",
            "source:task_6d5304648da4",
        ),
    ),
]

B9_PROD_SHAPED_TASK_IDS: list[str] = [t.task_id for t in B9_PROD_SHAPED_TASKS]

__all__ = [
    "B9_PROD_SHAPED_TASKS",
    "B9_PROD_SHAPED_TASK_IDS",
]
