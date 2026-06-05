"""Architecture test: butler/transport/llm_client.py must not import from butler.core.

Audit source: docs/reviews/project-deep-audit-2026-06-r1to8.md §R1-1 [C] layering_violation
File:line:    butler/transport/llm_client.py:360, 383, 476

The v4 architecture diagram places ``butler/transport/`` at the bottom of the
dependency graph. ``llm_client.py`` historically reached upward into
``butler.core.streaming_tools`` to fire streaming-tool dispatch callbacks,
which forced every transport test to pull up the entire core stack. The fix
moves that helper into ``butler/transport/streaming_signal.py`` so that
``llm_client`` no longer depends on ``butler.core``.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

import butler.transport.llm_client as llm_client_module


@pytest.mark.module_test
def test_llm_client_module_does_not_import_from_butler_core():
    """llm_client.py source must not contain ``from butler.core`` imports."""
    source = inspect.getsource(llm_client_module)
    tree = ast.parse(source)
    offenders: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "butler.core" or module.startswith("butler.core."):
                offenders.append((module, node.lineno))
    assert not offenders, (
        "butler/transport/llm_client.py must not import from butler.core "
        "(layering violation, audit R1-1). Offending imports: "
        + ", ".join(f"{mod}:{ln}" for mod, ln in offenders)
    )


@pytest.mark.module_test
def test_llm_client_source_file_has_no_butler_core_imports():
    """Same invariant checked against the on-disk source file (catches REPL drift)."""
    src_path = pathlib.Path(llm_client_module.__file__)
    text = src_path.read_text(encoding="utf-8")
    assert "from butler.core" not in text, (
        f"{src_path} still contains a `from butler.core` import; "
        "R1-1 layering violation is not fully fixed."
    )


@pytest.mark.module_test
def test_streaming_signal_module_lives_in_transport():
    """The replacement helper must live in butler.transport, not butler.core."""
    from butler.transport import streaming_signal

    module_file = pathlib.Path(streaming_signal.__file__).resolve()
    assert module_file.parent.name == "transport", (
        f"streaming_signal.py should live in butler/transport/, found at {module_file}"
    )
    assert hasattr(streaming_signal, "notify_complete_tool_calls_from_stream"), (
        "butler.transport.streaming_signal must expose notify_complete_tool_calls_from_stream"
    )
