"""Architecture test: transport must not import from butler.ops.

Audit source: docs/reviews/project-deep-audit-2026-06-r1to8.md §R1-9 [H]
File:line:  butler/transport/stream_probe.py:52

The v4 architecture puts ``butler/transport/`` below ``butler/ops/`` in the
dependency graph. ``stream_probe`` historically lazy-imported
``butler.ops.runtime_metrics.observe_ms`` to record probe latency. That
coupling meant transport had to know about ops at runtime, defeating the
layering that lets CLI/Loop unit tests run without ops.

The fix introduces ``butler/core/metrics_sink.py`` with a :class:`MetricsSink`
Protocol and convenience shims (``observe_ms``, ``inc``). The ops side
registers a concrete implementation; transport (and any other core module)
only depends on the core Protocol.
"""

from __future__ import annotations

import ast
import pathlib

import pytest


_TRANSPORT_FILE = "butler/transport/stream_probe.py"


def _offending_imports(source: str) -> list[tuple[str, int]]:
    """Return (module, lineno) for every ``from butler.ops`` import in source."""
    tree = ast.parse(source)
    offenders: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "butler.ops" or module.startswith("butler.ops."):
                offenders.append((module, node.lineno))
    return offenders


@pytest.mark.module_test
def test_stream_probe_does_not_import_from_butler_ops():
    """AST scan: stream_probe must not import from butler.ops (R1-9)."""
    src_path = pathlib.Path(_TRANSPORT_FILE)
    text = src_path.read_text(encoding="utf-8")
    offenders = _offending_imports(text)
    assert not offenders, (
        f"{src_path} still has reverse imports to butler.ops "
        "(R1-9 layering violation). Offending imports: "
        + ", ".join(f"{mod}:{ln}" for mod, ln in offenders)
    )


@pytest.mark.module_test
def test_stream_probe_source_has_no_butler_ops_text():
    """On-disk text fallback: catches REPL drift where AST may differ from saved file."""
    src_path = pathlib.Path(_TRANSPORT_FILE)
    text = src_path.read_text(encoding="utf-8")
    assert "from butler.ops" not in text, (
        f"{src_path} still contains a `from butler.ops` import; "
        "R1-9 layering violation is not fully fixed."
    )
    assert "import butler.ops" not in text, (
        f"{src_path} still contains an `import butler.ops` statement; "
        "R1-9 layering violation is not fully fixed."
    )


@pytest.mark.module_test
def test_core_metrics_sink_module_exists():
    """The Protocol + shims must live in butler/core/metrics_sink.py."""
    import butler.core.metrics_sink as metrics_sink_module  # noqa: F401

    module_file = pathlib.Path(metrics_sink_module.__file__).resolve()
    assert module_file.parent.name == "core", (
        f"metrics_sink.py should live in butler/core/, found at {module_file}"
    )
    assert module_file.name == "metrics_sink.py"


@pytest.mark.module_test
def test_core_metrics_sink_exposes_required_symbols():
    """The metrics_sink module must export the Protocol, default sink, and shims."""
    from butler.core import metrics_sink

    required = (
        "MetricsSink",
        "NullMetricsSink",
        "observe_ms",
        "inc",
        "set_default_sink",
        "get_default_sink",
    )
    for name in required:
        assert hasattr(metrics_sink, name), (
            f"butler.core.metrics_sink is missing required export: {name}"
        )


@pytest.mark.module_test
def test_default_sink_is_null_sink():
    """Before ops wires itself in, the default sink must be the no-op.

    Order-sensitive: if any other test (or ops bootstrap) has installed a
    real sink, we explicitly reset to null for the assertion, then restore.
    """
    from butler.core.metrics_sink import (
        NullMetricsSink,
        get_default_sink,
        inc,
        observe_ms,
        set_default_sink,
    )

    saved = get_default_sink()
    try:
        set_default_sink(None)
        assert isinstance(get_default_sink(), NullMetricsSink), (
            "default sink must be NullMetricsSink"
        )
        # No-op behaviour: must not raise, must return None
        assert observe_ms("x", 1.0) is None
        assert observe_ms("x", -1.0) is None  # negative is also tolerated
        assert inc("y") is None
        assert inc("y", 5) is None
    finally:
        set_default_sink(saved)


@pytest.mark.module_test
def test_null_sink_implements_protocol():
    """NullMetricsSink must satisfy the MetricsSink Protocol (duck-typed)."""
    from butler.core.metrics_sink import MetricsSink, NullMetricsSink

    assert isinstance(NullMetricsSink(), MetricsSink), (
        "NullMetricsSink instance must satisfy MetricsSink Protocol"
    )


@pytest.mark.module_test
def test_set_default_sink_swaps_implementation():
    """set_default_sink must atomically replace the global sink; None resets."""
    from butler.core.metrics_sink import (
        NullMetricsSink,
        get_default_sink,
        inc,
        observe_ms,
        set_default_sink,
    )

    class _Stub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple]] = []

        def observe_ms(self, name, milliseconds):
            self.calls.append(("observe_ms", (name, milliseconds)))

        def inc(self, name, value=1):
            self.calls.append(("inc", (name, value)))

    saved = get_default_sink()
    try:
        stub = _Stub()
        set_default_sink(stub)

        observe_ms("lat", 12.5)
        inc("counter")
        inc("counter", 3)

        assert len(stub.calls) == 3
        assert stub.calls[0] == ("observe_ms", ("lat", 12.5))
        assert stub.calls[1] == ("inc", ("counter", 1))
        assert stub.calls[2] == ("inc", ("counter", 3))

        # reset back to no-op
        set_default_sink(None)
        assert isinstance(get_default_sink(), NullMetricsSink)
    finally:
        set_default_sink(saved)


@pytest.mark.module_test
def test_shims_swallow_sink_exceptions():
    """If a sink raises, the shim must not propagate (best-effort)."""
    from butler.core.metrics_sink import (
        get_default_sink,
        inc,
        observe_ms,
        set_default_sink,
    )

    class _Exploding:
        def observe_ms(self, name, milliseconds):
            raise RuntimeError("boom")

        def inc(self, name, value=1):
            raise RuntimeError("boom")

    saved = get_default_sink()
    try:
        set_default_sink(_Exploding())
        # These must not raise even though the sink raises
        assert observe_ms("x", 1.0) is None
        assert inc("y") is None
    finally:
        set_default_sink(saved)


@pytest.mark.module_test
def test_arbitrary_class_with_methods_satisfies_protocol():
    """Structural Protocol: any class with the two methods conforms."""
    from butler.core.metrics_sink import MetricsSink

    class _Duck:
        def observe_ms(self, name, milliseconds):
            pass

        def inc(self, name, value=1):
            pass

    assert isinstance(_Duck(), MetricsSink), (
        "any class with observe_ms + inc methods must satisfy MetricsSink"
    )
