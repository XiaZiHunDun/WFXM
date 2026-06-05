"""Architecture test: butler/core/agent_loop.py must not import from butler.gateway.

Audit source: docs/reviews/project-deep-audit-2026-06-r1to8.md §R1-2 [C] layering_violation
File:line:    butler/core/agent_loop.py:143

The v4 architecture diagram places ``butler/core/`` below ``butler/gateway/`` in
the dependency graph. ``agent_loop.py`` historically lazy-imported
``merge_loop_callbacks`` from ``butler.gateway.outbound_bridge`` on every
``run()`` invocation when ``run_callbacks`` were provided. That made core
silently depend on gateway and forced CLI / unit-test paths to keep gateway
modules importable.

The fix moves ``merge_loop_callbacks`` (a pure ``LoopCallbacks`` merger that
has no gateway dependencies) into ``butler/core/loop_callbacks_merge.py``.
``butler.gateway.outbound_bridge`` keeps a re-export for backward
compatibility.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

import butler.core.agent_loop as agent_loop_module


@pytest.mark.module_test
def test_agent_loop_module_does_not_import_from_butler_gateway():
    """agent_loop.py source must not contain ``from butler.gateway`` imports.

    Both top-level and function-local (lazy) imports are forbidden. R1-2 is a
    layering violation specifically because the lazy import inside ``run()``
    still couples ``butler.core.agent_loop`` to ``butler.gateway`` on every
    turn.
    """
    source = inspect.getsource(agent_loop_module)
    tree = ast.parse(source)
    offenders: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "butler.gateway" or module.startswith("butler.gateway."):
                offenders.append((module, node.lineno))
    assert not offenders, (
        "butler/core/agent_loop.py must not import from butler.gateway "
        "(layering violation, audit R1-2). Offending imports: "
        + ", ".join(f"{mod}:{ln}" for mod, ln in offenders)
    )


@pytest.mark.module_test
def test_agent_loop_source_file_has_no_butler_gateway_imports():
    """Same invariant checked against the on-disk source file (catches REPL drift)."""
    src_path = pathlib.Path(agent_loop_module.__file__)
    text = src_path.read_text(encoding="utf-8")
    assert "from butler.gateway" not in text, (
        f"{src_path} still contains a `from butler.gateway` import; "
        "R1-2 layering violation is not fully fixed."
    )
    assert "import butler.gateway" not in text, (
        f"{src_path} still contains an `import butler.gateway` statement; "
        "R1-2 layering violation is not fully fixed."
    )


@pytest.mark.module_test
def test_merge_loop_callbacks_lives_in_core():
    """The replacement helper must be importable from butler.core."""
    from butler.core.loop_callbacks_merge import merge_loop_callbacks

    module_file = pathlib.Path(
        __import__("butler.core.loop_callbacks_merge", fromlist=["__file__"]).__file__
    ).resolve()
    assert module_file.parent.name == "core", (
        f"loop_callbacks_merge.py should live in butler/core/, found at {module_file}"
    )
    assert callable(merge_loop_callbacks), (
        "butler.core.loop_callbacks_merge.merge_loop_callbacks must be callable"
    )


@pytest.mark.module_test
def test_merge_loop_callbacks_behaviour_preserved():
    """The relocated helper must still behave like the pre-fix gateway version."""
    from butler.core.loop_callbacks_merge import merge_loop_callbacks
    from butler.core.loop_types import LoopCallbacks

    base = LoopCallbacks(on_llm_start=lambda msgs: None)
    extra = LoopCallbacks(on_tool_start=lambda name, args: None)
    merged = merge_loop_callbacks(base, extra)
    assert merged is not base
    assert merged is not extra
    assert merged.on_llm_start is base.on_llm_start, "base value must be preserved when extra is None"
    assert merged.on_tool_start is extra.on_tool_start, "extra value must override when set"

    # extra=None returns base unchanged
    assert merge_loop_callbacks(base, None) is base
    # base=None returns extra unchanged
    assert merge_loop_callbacks(None, extra) is extra


@pytest.mark.module_test
def test_gateway_outbound_bridge_still_reexports_merge_loop_callbacks():
    """Gateway must keep re-exporting for backward compatibility with existing callers."""
    from butler.gateway.outbound_bridge import merge_loop_callbacks as gateway_merge
    from butler.core.loop_callbacks_merge import merge_loop_callbacks as core_merge

    assert gateway_merge is core_merge, (
        "butler.gateway.outbound_bridge.merge_loop_callbacks must be the same "
        "object as butler.core.loop_callbacks_merge.merge_loop_callbacks (re-export)."
    )


# -----------------------------------------------------------------------
# R1-2 part 2: tools.interrupt 沉到 core.interrupt
# -----------------------------------------------------------------------
# 审计 R1-2 同时点名了 agent_loop.py 顶层的 "from butler.tools.interrupt"
# (line 27 当时),audit 结论是 interrupt 模块本身只是线程局部信号,
# 无 tool 语义,应下沉到 core/interrupt.py。
#
# 上一 commit (4aea3b0) 只修了 merge_loop_callbacks 一行,
# 本次补做 interrupt 下沉:
#   - core/agent_loop.py 改 import 源
#   - 新建 core/interrupt.py(原 tools/interrupt.py 内容)
#   - tools/interrupt.py 留一行 re-export 以兼容 terminal_impl.py /
#     test_hermes_extraction.py 的既有 import 点
# -----------------------------------------------------------------------


@pytest.mark.module_test
def test_agent_loop_source_file_has_no_tools_interrupt_import():
    """agent_loop.py must not import from butler.tools.interrupt (R1-2 part 2).

    The interrupt signal is a thread-local set, not a tool. ``core/`` should
    not depend on ``tools/`` for this primitive.
    """
    src_path = pathlib.Path(agent_loop_module.__file__)
    text = src_path.read_text(encoding="utf-8")
    assert "from butler.tools.interrupt" not in text, (
        f"{src_path} still imports from butler.tools.interrupt; "
        "R1-2 part 2 layering violation is not fixed."
    )
    assert "import butler.tools.interrupt" not in text, (
        f"{src_path} still has a `import butler.tools.interrupt` statement; "
        "R1-2 part 2 layering violation is not fixed."
    )


@pytest.mark.module_test
def test_core_interrupt_module_exists():
    """The interrupt primitive must live in butler/core/interrupt.py."""
    import butler.core.interrupt as core_interrupt  # noqa: F401

    module_file = pathlib.Path(
        __import__("butler.core.interrupt", fromlist=["__file__"]).__file__
    ).resolve()
    assert module_file.parent.name == "core", (
        f"interrupt.py should live in butler/core/, found at {module_file}"
    )
    assert module_file.name == "interrupt.py", (
        f"expected interrupt.py, found {module_file.name}"
    )


@pytest.mark.module_test
def test_core_interrupt_exposes_three_primitives():
    """core.interrupt must export set_interrupt, clear_interrupt, is_interrupted."""
    from butler.core import interrupt as core_interrupt

    for name in ("set_interrupt", "clear_interrupt", "is_interrupted"):
        assert hasattr(core_interrupt, name), (
            f"butler.core.interrupt is missing required export: {name}"
        )
        assert callable(getattr(core_interrupt, name)), (
            f"butler.core.interrupt.{name} must be callable"
        )


@pytest.mark.module_test
def test_core_interrupt_reexport_matches_tools_reexport():
    """tools.interrupt (kept as backward-compat re-export) must point at core.

    ``butler.tools.terminal_impl`` and ``tests/test_hermes_extraction.py`` still
    import from ``butler.tools.interrupt``. To keep them green without
    duplicating logic, ``butler/tools/interrupt.py`` becomes a one-line
    re-export from ``butler.core.interrupt``.
    """
    from butler.core import interrupt as core_interrupt
    from butler.tools import interrupt as tools_interrupt

    assert tools_interrupt.set_interrupt is core_interrupt.set_interrupt
    assert tools_interrupt.clear_interrupt is core_interrupt.clear_interrupt
    assert tools_interrupt.is_interrupted is core_interrupt.is_interrupted
