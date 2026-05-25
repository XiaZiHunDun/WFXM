"""Preemptive compaction routing (OpenClaw OC-P0)."""

from __future__ import annotations

import pytest

from butler.core.preemptive_compact import (
    ContextPrecheckOverflow,
    apply_preemptive_pipeline,
    preemptive_compact_enabled,
)


def _msgs(n: int = 5) -> list[dict]:
    out: list[dict] = []
    for i in range(n):
        out.extend([
            {"role": "user", "content": f"question {i} " + ("x" * 200)},
            {"role": "assistant", "content": f"answer {i} " + ("y" * 200)},
            {
                "role": "tool",
                "tool_call_id": f"c{i}",
                "content": "tool output " + ("z" * 3000),
            },
        ])
    return out


def test_preemptive_ok_under_threshold(monkeypatch):
    monkeypatch.setenv("BUTLER_PREEMPTIVE_COMPACT", "1")
    assert preemptive_compact_enabled()

    def est(msgs):
        return sum(len(str(m.get("content", ""))) for m in msgs) // 4

    out, dec = apply_preemptive_pipeline(
        [{"role": "user", "content": "hi"}],
        max_context_tokens=200_000,
        estimate_tokens=est,
        compress=lambda m: m,
    )
    assert dec.route == "ok"
    assert out[0]["content"] == "hi"


def test_preemptive_compact_route(monkeypatch):
    monkeypatch.setenv("BUTLER_PREEMPTIVE_COMPACT", "1")
    monkeypatch.delenv("BUTLER_DISABLE_AUTO_COMPACT", raising=False)
    compacted = {"called": False}

    def est(msgs):
        return 50_000 if not compacted["called"] else 1000

    def compress(msgs):
        compacted["called"] = True
        return [{"role": "user", "content": "summary"}]

    out, dec = apply_preemptive_pipeline(
        _msgs(5),
        max_context_tokens=10_000,
        estimate_tokens=est,
        compress=compress,
        diagnostics={},
    )
    assert compacted["called"]
    assert dec.route in ("compact", "truncate", "ok")
    assert len(out) >= 1


def test_overflow_raises_type():
    exc = ContextPrecheckOverflow("too big", estimated=99, threshold=10)
    assert exc.estimated_tokens == 99
    assert exc.threshold_tokens == 10
