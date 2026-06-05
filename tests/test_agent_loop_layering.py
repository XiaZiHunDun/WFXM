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
