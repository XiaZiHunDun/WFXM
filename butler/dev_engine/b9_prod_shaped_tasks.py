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

from butler.dev_engine.b9_types import B9TaskSpec
from butler.dev_engine.b9_verify_utils import pytest_verify as _pytest_verify


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
    from butler.dev_engine.edit_ops import apply_write

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
    return _pytest_verify(ws)


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
    from butler.dev_engine.edit_ops import apply_patch

    _rec, err = apply_patch(
        ws / "logic.py",
        "return x if x < upper else upper",
        "return x if x <= upper else upper",
    )
    if err:
        raise RuntimeError(err)


def _verify_b9l_prod_patch_wrong(ws: Path) -> tuple[bool, str]:
    return _pytest_verify(ws)


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
    from butler.dev_engine.edit_ops import apply_patch

    _rec, err = apply_patch(
        ws / "formatter.py",
        "return f'  {name}  '",
        "return f'  {name}  '.strip()",
    )
    if err:
        raise RuntimeError(err)


def _verify_b9l_prod_no_test(ws: Path) -> tuple[bool, str]:
    return _pytest_verify(ws)


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
    from butler.dev_engine.edit_ops import apply_patch

    _rec, err = apply_patch(
        ws / "greet.py",
        "return 'hi'",
        "return 'hello'",
    )
    if err:
        raise RuntimeError(err)


def _verify_b9l_prod_demo_fix_greet_return(ws: Path) -> tuple[bool, str]:
    return _pytest_verify(ws)


def _setup_b9l_prod_read_state_greet(ws: Path) -> None:
    _setup_b9l_prod_demo_fix_greet_return(ws)


def _oracle_b9l_prod_read_state_greet(ws: Path) -> None:
    _oracle_b9l_prod_demo_fix_greet_return(ws)


def _verify_b9l_prod_read_state_greet(ws: Path) -> tuple[bool, str]:
    return _pytest_verify(ws)


def _setup_b9l_prod_main_helpers_import(ws: Path) -> None:
    from butler.dev_engine.b9_live_fixed_tasks import _setup_b9l_multi_file_import

    _setup_b9l_multi_file_import(ws)


def _oracle_b9l_prod_main_helpers_import(ws: Path) -> None:
    from butler.dev_engine.b9_live_fixed_tasks import _oracle_b9l_multi_file_import

    _oracle_b9l_multi_file_import(ws)


def _verify_b9l_prod_main_helpers_import(ws: Path) -> tuple[bool, str]:
    return _pytest_verify(ws)


def _setup_b9l_prod_cross_module_rename(ws: Path) -> None:
    from butler.dev_engine.b9_live_fixed_tasks import _setup_b9l_cross_module_rename

    _setup_b9l_cross_module_rename(ws)


def _oracle_b9l_prod_cross_module_rename(ws: Path) -> None:
    from butler.dev_engine.b9_live_fixed_tasks import _oracle_b9l_cross_module_rename

    _oracle_b9l_cross_module_rename(ws)


def _verify_b9l_prod_cross_module_rename(ws: Path) -> tuple[bool, str]:
    return _pytest_verify(ws)


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
    from butler.dev_engine.edit_ops import apply_patch

    _rec, err = apply_patch(
        ws / "demo" / "hello.py",
        "return a - b",
        "return a + b",
    )
    if err:
        raise RuntimeError(err)


def _verify_b9l_prod_lingwen_demo_add(ws: Path) -> tuple[bool, str]:
    return _pytest_verify(ws)


_READ_STATE_CONTEXT = (
    "## PRODUCTION LESSON (READ_STATE_REQUIRED)\n"
    "Previous delegate failed because patch/write ran before read_file.\n"
    "Mandatory: read_file greet.py AND test_b9.py first, then patch greet.py only."
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
]

B9_PROD_SHAPED_TASK_IDS: list[str] = [t.task_id for t in B9_PROD_SHAPED_TASKS]

__all__ = [
    "B9_PROD_SHAPED_TASKS",
    "B9_PROD_SHAPED_TASK_IDS",
]
