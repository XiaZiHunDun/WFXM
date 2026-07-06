"""B9 LIVE fixed benchmark set — 10 curated delegate tasks.

Used by ``butler-eval-b9-live.sh`` for weekly LLM end-to-end evaluation.
Oracle mode must pass for CI regression (including ``expect_pass=False`` STUCK).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from butler.dev_engine.b9_types import B9TaskSpec
from butler.dev_engine.b9_verify_utils import pytest_verify as _pytest_verify


def _verify_ws(ws: Path) -> tuple[bool, str]:
    return cast(tuple[bool, str], _pytest_verify(ws))


# ── B9L_multi_file_import ───────────────────────────────────────


def _setup_b9l_multi_file_import(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "helpers.py").write_text(
        "def run():\n    return 42\n",
        encoding="utf-8",
    )
    (ws / "main.py").write_text(
        "from helper import run\n\n\ndef main():\n    return run()\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from main import main\n\n\ndef test_main():\n    assert main() == 42\n",
        encoding="utf-8",
    )


def _oracle_b9l_multi_file_import(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_patch

    _rec, err = apply_patch(ws / "main.py", "from helper import run", "from helpers import run")
    if err:
        raise RuntimeError(err)


def _verify_b9l_multi_file_import(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


# ── B9L_pytest_fix_impl ─────────────────────────────────────────


def _setup_b9l_pytest_fix_impl(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "calc.py").write_text(
        "def mul(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from calc import mul\n\n\ndef test_mul():\n    assert mul(2, 3) == 6\n",
        encoding="utf-8",
    )


def _oracle_b9l_pytest_fix_impl(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_patch

    _rec, err = apply_patch(ws / "calc.py", "a + b", "a * b")
    if err:
        raise RuntimeError(err)


def _verify_b9l_pytest_fix_impl(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


# ── B9L_stuck_unsolvable (expect_pass=False) ────────────────────


def _setup_b9l_stuck_unsolvable(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "broken.py").write_text(
        "def compute():\n    raise NotImplementedError('requires missing native lib')\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from broken import compute\n\n\ndef test_compute():\n    assert compute() == 1\n",
        encoding="utf-8",
    )


def _oracle_b9l_stuck_unsolvable(ws: Path) -> None:
    """No fix — task should remain failing."""


def _verify_b9l_stuck_unsolvable(ws: Path) -> tuple[bool, str]:
    ok, _msg = _pytest_verify(ws)
    return ok, "unexpectedly fixed" if ok else "still failing as expected"


# ── B9L_cross_module_rename ─────────────────────────────────────


def _setup_b9l_cross_module_rename(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "pkg"
    pkg.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text(
        "from pkg.client import Client\n\n__all__ = ['Client']\n",
        encoding="utf-8",
    )
    (pkg / "client.py").write_text(
        "class Client:\n    def getData(self):\n        return {}\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from pkg.client import Client\n\n\ndef test_rename():\n"
        "    c = Client()\n    assert hasattr(c, 'get_data')\n"
        "    assert not hasattr(c, 'getData')\n",
        encoding="utf-8",
    )


def _oracle_b9l_cross_module_rename(ws: Path) -> None:
    text = (ws / "pkg" / "client.py").read_text(encoding="utf-8")
    (ws / "pkg" / "client.py").write_text(text.replace("getData", "get_data"), encoding="utf-8")


def _verify_b9l_cross_module_rename(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


# ── B9L_test_driven_add ─────────────────────────────────────────


def _setup_b9l_test_driven_add(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "service.py").write_text(
        "# ping not implemented yet\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from service import ping\n\n\ndef test_ping():\n    assert ping() == 'pong'\n",
        encoding="utf-8",
    )


def _oracle_b9l_test_driven_add(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_write

    _rec, err = apply_write(
        ws / "service.py",
        "def ping():\n    return 'pong'\n",
    )
    if err:
        raise RuntimeError(err)


def _verify_b9l_test_driven_add(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


# ── B9L_two_file_patch ──────────────────────────────────────────


def _setup_b9l_two_file_patch(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "config.py").write_text("THRESHOLD = 10\n", encoding="utf-8")
    (ws / "filter.py").write_text(
        "from config import THRESHOLD\n\n\ndef keep(x):\n    return x > THRESHOLD\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from filter import keep\n\n\ndef test_keep():\n"
        "    assert keep(5) is False\n    assert keep(15) is True\n",
        encoding="utf-8",
    )


def _oracle_b9l_two_file_patch(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_patch

    _rec, err = apply_patch(ws / "config.py", "THRESHOLD = 10", "THRESHOLD = 5")
    if err:
        raise RuntimeError(err)


def _verify_b9l_two_file_patch(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


# ── B9L_add_missing_method ──────────────────────────────────────


def _setup_b9l_add_missing_method(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "store.py").write_text(
        "class Store:\n    def put(self, k, v):\n        self._data = {k: v}\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from store import Store\n\n\ndef test_get():\n"
        "    s = Store()\n    s.put('a', 1)\n    assert s.get('a') == 1\n",
        encoding="utf-8",
    )


def _oracle_b9l_add_missing_method(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_patch

    old = "    def put(self, k, v):\n        self._data = {k: v}\n"
    new = (
        "    def __init__(self):\n        self._data = {}\n\n"
        "    def put(self, k, v):\n        self._data[k] = v\n\n"
        "    def get(self, k):\n        return self._data[k]\n"
    )
    _rec, err = apply_patch(ws / "store.py", old, new)
    if err:
        raise RuntimeError(err)


def _verify_b9l_add_missing_method(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


# ── B9L_fix_exception_handler ───────────────────────────────────


def _setup_b9l_fix_exception_handler(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "parser.py").write_text(
        "def parse_int(text):\n    try:\n        return int(text)\n"
        "    except:\n        return None\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "import pytest\nfrom parser import parse_int\n\n"
        "def test_parse():\n    assert parse_int('3') == 3\n\n"
        "def test_parse_bad():\n    with pytest.raises(ValueError):\n"
        "        parse_int('x')\n",
        encoding="utf-8",
    )


def _oracle_b9l_fix_exception_handler(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_patch

    old = "    except:\n        return None\n"
    new = "    except ValueError:\n        raise\n"
    _rec, err = apply_patch(ws / "parser.py", old, new)
    if err:
        raise RuntimeError(err)


def _verify_b9l_fix_exception_handler(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


# ── B9L_extract_constant ────────────────────────────────────────


def _setup_b9l_extract_constant(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "app.py").write_text(
        "MAX_RETRIES = 3\n\n\ndef should_retry(n):\n    return n < MAX_RETRIES\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from app import should_retry, MAX_RETRIES\n\n"
        "def test_retry():\n    assert should_retry(2) is True\n"
        "    assert MAX_RETRIES == 3\n",
        encoding="utf-8",
    )


def _oracle_b9l_extract_constant(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_write

    (ws / "constants.py").write_text("MAX_RETRIES = 3\n", encoding="utf-8")
    (ws / "app.py").write_text(
        "from constants import MAX_RETRIES\n\n\ndef should_retry(n):\n"
        "    return n < MAX_RETRIES\n",
        encoding="utf-8",
    )


def _verify_b9l_extract_constant(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


# ── B9L_fix_off_by_one_loop ─────────────────────────────────────


def _setup_b9l_fix_off_by_one_loop(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "loops.py").write_text(
        "def sum_until(n):\n    total = 0\n    for i in range(n + 1):\n"
        "        total += i\n    return total\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from loops import sum_until\n\n\ndef test_sum_until():\n"
        "    assert sum_until(4) == 6\n",
        encoding="utf-8",
    )


def _oracle_b9l_fix_off_by_one_loop(ws: Path) -> None:
    from butler.dev_engine.edit_ops import apply_patch

    _rec, err = apply_patch(ws / "loops.py", "range(n + 1)", "range(n)")
    if err:
        raise RuntimeError(err)


def _verify_b9l_fix_off_by_one_loop(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


B9_LIVE_FIXED_TASKS: list[B9TaskSpec] = [
    B9TaskSpec(
        task_id="B9L_multi_file_import",
        description="Delegate dev: fix cross-module import (helper→helpers)",
        delegate_prompt=(
            "Fix main.py so it imports from helpers.py correctly. "
            "Tests in test_b9.py must pass. Only edit files in this workspace."
        ),
        setup=_setup_b9l_multi_file_import,
        verify=_verify_b9l_multi_file_import,
        oracle_apply=_oracle_b9l_multi_file_import,
        tags=("multi_file", "pytest"),
    ),
    B9TaskSpec(
        task_id="B9L_pytest_fix_impl",
        description="Delegate dev: fix mul() to pass pytest",
        delegate_prompt=(
            "Fix calc.py so test_b9.py passes (mul should multiply, not add)."
        ),
        setup=_setup_b9l_pytest_fix_impl,
        verify=_verify_b9l_pytest_fix_impl,
        oracle_apply=_oracle_b9l_pytest_fix_impl,
        tags=("pytest", "logic_bug"),
    ),
    B9TaskSpec(
        task_id="B9L_stuck_unsolvable",
        description="Delegate dev: unsolvable NotImplementedError (expect STUCK)",
        delegate_prompt=(
            "Implement compute() in broken.py so tests pass without external native libraries."
        ),
        setup=_setup_b9l_stuck_unsolvable,
        verify=_verify_b9l_stuck_unsolvable,
        oracle_apply=_oracle_b9l_stuck_unsolvable,
        expect_pass=False,
        tags=("stuck", "pytest"),
    ),
    B9TaskSpec(
        task_id="B9L_cross_module_rename",
        description="Delegate dev: rename getData→get_data across pkg",
        delegate_prompt=(
            "Rename method getData to get_data in pkg/client.py and update pkg/__init__.py. "
            "test_b9.py must pass."
        ),
        setup=_setup_b9l_cross_module_rename,
        verify=_verify_b9l_cross_module_rename,
        oracle_apply=_oracle_b9l_cross_module_rename,
        tags=("multi_file", "refactor", "pytest"),
    ),
    B9TaskSpec(
        task_id="B9L_test_driven_add",
        description="Delegate dev: add ping() to satisfy test",
        delegate_prompt="Add ping() to service.py so test_b9.py passes.",
        setup=_setup_b9l_test_driven_add,
        verify=_verify_b9l_test_driven_add,
        oracle_apply=_oracle_b9l_test_driven_add,
        tags=("pytest", "add_function"),
    ),
    B9TaskSpec(
        task_id="B9L_two_file_patch",
        description="Delegate dev: adjust THRESHOLD in config.py",
        delegate_prompt=(
            "Fix filter behavior by editing config.py so test_b9.py passes "
            "(keep(5) should be False)."
        ),
        setup=_setup_b9l_two_file_patch,
        verify=_verify_b9l_two_file_patch,
        oracle_apply=_oracle_b9l_two_file_patch,
        tags=("multi_file", "pytest"),
    ),
    B9TaskSpec(
        task_id="B9L_add_missing_method",
        description="Delegate dev: add Store.get() method",
        delegate_prompt="Add get() to Store in store.py so test_b9.py passes.",
        setup=_setup_b9l_add_missing_method,
        verify=_verify_b9l_add_missing_method,
        oracle_apply=_oracle_b9l_add_missing_method,
        tags=("pytest", "add_function"),
    ),
    B9TaskSpec(
        task_id="B9L_fix_exception_handler",
        description="Delegate dev: narrow bare except to ValueError",
        delegate_prompt=(
            "Fix parser.py: bare except should not swallow ValueError; test_b9.py must pass."
        ),
        setup=_setup_b9l_fix_exception_handler,
        verify=_verify_b9l_fix_exception_handler,
        oracle_apply=_oracle_b9l_fix_exception_handler,
        tags=("pytest", "error_handling", "T06"),
    ),
    B9TaskSpec(
        task_id="B9L_extract_constant",
        description="Delegate dev: extract MAX_RETRIES to constants.py",
        delegate_prompt=(
            "Move MAX_RETRIES from app.py to constants.py and fix imports. "
            "test_b9.py must pass."
        ),
        setup=_setup_b9l_extract_constant,
        verify=_verify_b9l_extract_constant,
        oracle_apply=_oracle_b9l_extract_constant,
        tags=("multi_file", "refactor", "pytest"),
    ),
    B9TaskSpec(
        task_id="B9L_fix_off_by_one_loop",
        description="Delegate dev: fix off-by-one in sum_until loop",
        delegate_prompt="Fix sum_until in loops.py so test_b9.py passes (sum 0..n inclusive).",
        setup=_setup_b9l_fix_off_by_one_loop,
        verify=_verify_b9l_fix_off_by_one_loop,
        oracle_apply=_oracle_b9l_fix_off_by_one_loop,
        tags=("pytest", "logic_bug"),
    ),
]

from butler.dev_engine.b9_prod_shaped_tasks import (  # noqa: E402
    B9_PROD_SHAPED_TASKS,
    B9_PROD_SHAPED_TASK_IDS,
)

B9_LIVE_FIXED_TASKS.extend(B9_PROD_SHAPED_TASKS)
B9_LIVE_FIXED_TASK_IDS: list[str] = [t.task_id for t in B9_LIVE_FIXED_TASKS]

__all__ = [
    "B9_LIVE_FIXED_TASKS",
    "B9_LIVE_FIXED_TASK_IDS",
    "B9_PROD_SHAPED_TASK_IDS",
    "B9_PROD_SHAPED_TASKS",
]
