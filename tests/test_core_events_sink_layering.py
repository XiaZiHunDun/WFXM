"""Architecture test: three core modules must not import from butler.gateway.

Audit source: docs/reviews/project-deep-audit-2026-06-r1to8.md §R1-3 [C]
Files:line:  butler/core/context_compressor.py:426
            butler/core/compaction_task.py:80, 130, 162
            butler/core/compaction_steer_bridge.py:33

The v4 architecture puts ``butler/core/`` below ``butler/gateway/`` in the
dependency graph. Three core modules historically lazy-imported gateway
facilities (``hooks.invoke_hook``, ``item_events.context_compaction_item`` /
``emit_thread_item``, ``message_queue.pop_urgent_inbound``) on every compact
turn. That coupling meant CLI / Loop unit tests could not run without
gateway being importable.

The fix introduces ``butler/core/events_sink.py`` with an :class:`EventsSink`
Protocol and convenience shims (``invoke_hook``, ``emit_context_compaction``,
``pop_urgent_inbound``). The gateway side registers a concrete
implementation; core modules only depend on the core Protocol.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest


_CORE_FILES = (
    "butler/core/context_compressor.py",
    "butler/core/compaction_task.py",
    "butler/core/compaction_steer_bridge.py",
)


def _offending_imports(source: str) -> list[tuple[str, int]]:
    """Return (module, lineno) for every ``from butler.gateway`` import in source."""
    tree = ast.parse(source)
    offenders: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "butler.gateway" or module.startswith("butler.gateway."):
                offenders.append((module, node.lineno))
    return offenders


@pytest.mark.module_test
@pytest.mark.parametrize("rel_path", _CORE_FILES)
def test_core_module_does_not_import_from_butler_gateway(rel_path: str):
    """AST scan: no core module may import from butler.gateway (R1-3)."""
    src_path = pathlib.Path(rel_path)
    text = src_path.read_text(encoding="utf-8")
    offenders = _offending_imports(text)
    assert not offenders, (
        f"{src_path} still has reverse imports to butler.gateway "
        "(R1-3 layering violation). Offending imports: "
        + ", ".join(f"{mod}:{ln}" for mod, ln in offenders)
    )


@pytest.mark.module_test
@pytest.mark.parametrize("rel_path", _CORE_FILES)
def test_core_module_source_has_no_butler_gateway_text(rel_path: str):
    """On-disk text fallback: catches REPL drift where AST may differ from saved file."""
    src_path = pathlib.Path(rel_path)
    text = src_path.read_text(encoding="utf-8")
    assert "from butler.gateway" not in text, (
        f"{src_path} still contains a `from butler.gateway` import; "
        "R1-3 layering violation is not fully fixed."
    )
    assert "import butler.gateway" not in text, (
        f"{src_path} still contains an `import butler.gateway` statement; "
        "R1-3 layering violation is not fully fixed."
    )


@pytest.mark.module_test
def test_core_events_sink_module_exists():
    """The Protocol + shims must live in butler/core/events_sink.py."""
    import butler.core.events_sink as events_sink_module  # noqa: F401

    module_file = pathlib.Path(events_sink_module.__file__).resolve()
    assert module_file.parent.name == "core", (
        f"events_sink.py should live in butler/core/, found at {module_file}"
    )
    assert module_file.name == "events_sink.py"


@pytest.mark.module_test
def test_core_events_sink_exposes_required_symbols():
    """The events_sink module must export the Protocol, default sink, and shims."""
    from butler.core import events_sink

    required = (
        "EventsSink",
        "NullEventsSink",
        "UrgentInbound",
        "invoke_hook",
        "emit_context_compaction",
        "pop_urgent_inbound",
        "set_events_sink",
        "get_events_sink",
    )
    for name in required:
        assert hasattr(events_sink, name), (
            f"butler.core.events_sink is missing required export: {name}"
        )


@pytest.mark.module_test
def test_default_sink_is_null_sink():
    """Before gateway wires itself in, the default sink must be the no-op."""
    from butler.core.events_sink import (
        NullEventsSink,
        get_events_sink,
        pop_urgent_inbound,
        invoke_hook,
        emit_context_compaction,
    )

    sink = get_events_sink()
    assert isinstance(sink, NullEventsSink), (
        f"default sink must be NullEventsSink, got {type(sink).__name__}"
    )
    # No-op behaviour
    assert invoke_hook("pre_compact", messages=[]) == []
    assert (
        emit_context_compaction(
            phase="completed", thread_id="t", tokens_before=0, tokens_after=0
        )
        is None
    )
    assert pop_urgent_inbound("sess") is None


@pytest.mark.module_test
def test_null_sink_implements_protocol():
    """NullEventsSink must satisfy the EventsSink Protocol (duck-typed)."""
    from butler.core.events_sink import EventsSink, NullEventsSink

    assert isinstance(NullEventsSink(), EventsSink), (
        "NullEventsSink instance must satisfy EventsSink Protocol"
    )


@pytest.mark.module_test
def test_set_events_sink_swaps_implementation():
    """set_events_sink must atomically replace the global sink; None resets to no-op."""
    from butler.core.events_sink import (
        NullEventsSink,
        UrgentInbound,
        get_events_sink,
        set_events_sink,
    )

    class _Stub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def invoke_hook(self, name, **kwargs):
            self.calls.append((name, dict(kwargs)))
            return ["ok"]

        def emit_context_compaction(self, **kwargs):
            self.calls.append(("emit", dict(kwargs)))

        def pop_urgent_inbound(self, session_key):
            self.calls.append(("pop", {"session_key": session_key}))
            return UrgentInbound(text="hi")

    saved = get_events_sink()
    try:
        stub = _Stub()
        set_events_sink(stub)

        from butler.core.events_sink import (
            emit_context_compaction,
            invoke_hook,
            pop_urgent_inbound,
        )

        assert invoke_hook("pre_compact", foo=1) == ["ok"]
        emit_context_compaction(phase="completed")
        item = pop_urgent_inbound("sess")
        assert item is not None and item.text == "hi"
        assert len(stub.calls) == 3
        # reset back to no-op
        set_events_sink(None)
        assert isinstance(get_events_sink(), NullEventsSink)
    finally:
        set_events_sink(saved)
