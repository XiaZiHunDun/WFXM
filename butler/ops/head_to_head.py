"""Head-to-head scenario definitions (T1–T5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from butler.ops.head_to_head_common import HeadToHeadScenario, run_scenario

ROOT = Path(__file__).resolve().parents[2]

T1 = HeadToHeadScenario(
    id="t1",
    fixture=ROOT / "tests" / "fixtures" / "head_to_head_t1",
    session="cli:head-to-head-t1",
    chat_id="head-to-head-t1",
    category="head-to-head-t1",
    task=(
        "Fix calc.py: mul(a, b) must return a * b (multiply). "
        "test_calc.py expects mul(3, 4) == 12. "
        "Use read_file then patch on calc.py only; then run pytest on test_calc.py."
    ),
    context="""## Head-to-head T1 (patch only)
1. read_file calc.py and test_calc.py before edit.
2. patch calc.py: change `return a + b` to `return a * b`.
3. Verify with run_pytest on test_calc.py (preferred) or terminal pytest in this workspace.

Do not edit test_calc.py.""",
    pytest_args=["test_calc.py"],
    cc_prompt_template=(
        "You are in {ws}. Fix calc.py so mul(a,b) returns a*b not a+b. "
        "test_calc.py must pass. read the files first, patch calc.py only, "
        "then run: python3 -m pytest test_calc.py -q\n"
        "Initial pytest failure:\n{fail_tail}"
    ),
)

T2 = HeadToHeadScenario(
    id="t2",
    fixture=ROOT / "tests" / "fixtures" / "head_to_head_t2",
    session="cli:head-to-head-t2",
    chat_id="head-to-head-t2",
    category="head-to-head-t2",
    task=(
        "Fix butler_sample/discount.py: apply_discount(price, rate) must return "
        "price * (1 - rate), not price - rate. "
        "tests/test_discount.py must pass. read_file then patch discount.py only."
    ),
    context="""## Head-to-head T2 — butler-style logic bug
1. read_file butler_sample/discount.py and tests/test_discount.py.
2. patch discount.py: `return price - rate` → `return price * (1 - rate)`.
3. run_pytest test_calc.py or pytest test_calc.py

Do not edit the test file.""",
    pytest_args=["tests/test_discount.py"],
    cc_prompt_template=(
        "You are in {ws}. Fix butler_sample/discount.py: apply_discount(price, rate) "
        "should return price * (1 - rate), not price - rate. "
        "Run: python3 -m pytest tests/test_discount.py -q\n"
        "Initial failure:\n{fail_tail}"
    ),
)

T3 = HeadToHeadScenario(
    id="t3",
    fixture=ROOT / "tests" / "fixtures" / "head_to_head_t3",
    session="cli:head-to-head-t3",
    chat_id="head-to-head-t3",
    category="head-to-head-t3",
    task=(
        "Rename Client.getData to get_data in pkg/client.py and update pkg/__init__.py "
        "if needed. test_pkg.py must pass. Use read_file then patch; do not edit test_pkg.py."
    ),
    context="""## Head-to-head T3 — cross-module rename (B9L_cross_module_rename class)
1. read_file pkg/client.py, pkg/__init__.py, test_pkg.py.
2. patch pkg/client.py: rename method getData → get_data.
3. run_pytest test_pkg.py or pytest test_pkg.py

Only edit under pkg/.""",
    pytest_args=["test_pkg.py"],
    cc_prompt_template=(
        "You are in {ws}. Rename method getData to get_data in pkg/client.py "
        "(snake_case). Update pkg/__init__.py if needed. test_pkg.py must pass. "
        "Read files first, then patch. Run: python3 -m pytest test_pkg.py -q\n"
        "Initial failure:\n{fail_tail}"
    ),
)

T4 = HeadToHeadScenario(
    id="t4",
    fixture=ROOT / "tests" / "fixtures" / "head_to_head_t4",
    session="cli:head-to-head-t4",
    chat_id="head-to-head-t4",
    category="head-to-head-t4",
    task=(
        "Implement add(a, b) in lib.py so test_lib.py passes. "
        "The test imports add from lib and expects add(2, 3) == 5. "
        "Use read_file then write_file or patch on lib.py only; do not edit test_lib.py."
    ),
    context="""## Head-to-head T4 — test-driven add function (B9L_test_driven_add class)
1. read_file test_lib.py and lib.py.
2. implement `def add(a, b): return a + b` in lib.py (write_file or patch).
3. run_pytest test_lib.py or pytest test_lib.py

Do not edit test_lib.py.""",
    pytest_args=["test_lib.py"],
    cc_prompt_template=(
        "You are in {ws}. Implement add(a, b) in lib.py so test_lib.py passes "
        "(add(2, 3) must equal 5). Read test_lib.py and lib.py first, then patch or "
        "write lib.py only. Run: python3 -m pytest test_lib.py -q\n"
        "Initial failure:\n{fail_tail}"
    ),
)

T5 = HeadToHeadScenario(
    id="t5",
    fixture=ROOT / "tests" / "fixtures" / "head_to_head_t5",
    session="cli:head-to-head-t5",
    chat_id="head-to-head-t5",
    category="head-to-head-t5",
    task=(
        "Fix demo/hello.py in this LingWen1-shaped workspace: add(a, b) must return a + b, "
        "not a - b. test_demo.py must pass. read_file then patch demo/hello.py only; "
        "do not edit test_demo.py or docs."
    ),
    context="""## Head-to-head T5 — LingWen demo logic fix (B9L_prod_lingwen_demo_add class)
1. read_file test_demo.py and demo/hello.py.
2. patch demo/hello.py: fix add() to return a + b.
3. run_pytest test_demo.py or pytest test_demo.py

Non-docs code change only under demo/.""",
    pytest_args=["test_demo.py"],
    cc_prompt_template=(
        "You are in {ws}. LingWen1 demo: fix add(a,b) in demo/hello.py — it wrongly returns "
        "a-b; should return a+b. test_demo.py must pass. Read files first, patch hello.py only. "
        "Run: python3 -m pytest test_demo.py -q\n"
        "Initial failure:\n{fail_tail}"
    ),
)

SCENARIOS = {"t1": T1, "t2": T2, "t3": T3, "t4": T4, "t5": T5}


def run_head_to_head_t1(**kwargs: Any) -> dict[str, Any]:
    return cast(dict[str, Any], run_scenario(T1, **kwargs))


def run_head_to_head_t2(**kwargs: Any) -> dict[str, Any]:
    return cast(dict[str, Any], run_scenario(T2, **kwargs))


def run_head_to_head_t3(**kwargs: Any) -> dict[str, Any]:
    return cast(dict[str, Any], run_scenario(T3, **kwargs))


def run_head_to_head_t4(**kwargs: Any) -> dict[str, Any]:
    return cast(dict[str, Any], run_scenario(T4, **kwargs))


def run_head_to_head_t5(**kwargs: Any) -> dict[str, Any]:
    return cast(dict[str, Any], run_scenario(T5, **kwargs))


__all__ = [
    "T1",
    "T2",
    "T3",
    "T4",
    "T5",
    "SCENARIOS",
    "run_head_to_head_t1",
    "run_head_to_head_t2",
    "run_head_to_head_t3",
    "run_head_to_head_t4",
    "run_head_to_head_t5",
]
