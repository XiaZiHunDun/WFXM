"""R1-18: lazy ``from butler.*`` import budget."""

from __future__ import annotations

from butler.ops.lazy_import_budget import LAZY_IMPORT_BUDGET, count_lazy_butler_imports


def test_lazy_import_count_within_budget():
    count = count_lazy_butler_imports()
    assert count <= LAZY_IMPORT_BUDGET, (
        f"lazy from-butler imports={count} exceeds budget {LAZY_IMPORT_BUDGET}; "
        "reduce lazy imports or lower budget in lazy_import_budget.py after intentional cleanup"
    )


def test_lazy_import_counter_ignores_module_level():
    from butler.ops.lazy_import_budget import count_module_level_butler_imports

    lazy = count_lazy_butler_imports()
    module = count_module_level_butler_imports()
    assert lazy < lazy + module
    assert module > 0


def test_call_llm_with_retry_under_line_budget():
    """ENG direction C: orchestrator stays thin after submodule split."""
    import inspect

    from butler.core.llm_retry import call_llm_with_retry

    lines = len(inspect.getsourcelines(call_llm_with_retry)[0])
    assert lines <= 150, f"call_llm_with_retry grew to {lines} lines"
