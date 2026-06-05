"""R2-9 [H]: agent_loop plugin/middleware skip errors must surface to diagnostics.

Audit source: docs/reviews/project-deep-audit-2026-06-r1to8.md §R2-9
File:line:    butler/core/agent_loop.py:71, 117, 260, 299, 392, 477, 491

The audit flagged 17 except-sites across agent_loop.py + agent_loop_phases.py.
After the R1-4 module split, ``agent_loop.py`` has 7 sites; the other 10 live
in ``agent_loop_phases.py`` (R1-owned, out of scope for R2-9).

This file covers the 7 in-scope sites:

- Line 71 (``_doom_loop_block_on_ask``): already fail-closed + ``logger.exception``.
  Skipped here; verified by existing doom-loop tests.
- Lines 117 / 260 / 299 / 491: had ``logger.debug(..., exc_info=True)`` — too quiet
  in production.  Must now use ``_record_skipped_plugin`` which records to
  ``self.diagnostics["skipped"]`` at ERROR level with full traceback.
- Lines 392 / 477: had ``logger.warning(...)`` *without* ``exc_info`` — the bigger
  bug per audit.  Must now also call ``_record_skipped_plugin``.

The shared helper ``AgentLoop._record_skipped_plugin`` caps the diagnostics
list at 50 to prevent unbounded growth across long-lived sessions.
"""

from __future__ import annotations

import logging

import pytest

from butler.core.agent_loop import AgentLoop, LoopConfig
from butler.core.loop_types import LoopCallbacks


# ---------- helpers ----------

def _make_client():
    from butler.transport.llm_client import LLMClient

    return LLMClient(provider="test", model="test-model")


def _make_loop(*, enable_guardrails: bool = True) -> AgentLoop:
    return AgentLoop(
        _make_client(),
        config=LoopConfig(stream=False, enable_guardrails=enable_guardrails),
        callbacks=LoopCallbacks(),
    )


# ---------- Commit 1: helper + 4 quiet sites ----------

class TestRecordSkippedPluginHelper:
    """Direct unit tests for ``AgentLoop._record_skipped_plugin``."""

    def test_logs_error_with_exc_info(self, caplog):
        loop = _make_loop()
        with caplog.at_level(logging.DEBUG, logger="butler.core.agent_loop"):
            loop._record_skipped_plugin("test_plugin", ValueError("boom"))
        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors, (
            f"expected at least one ERROR record, got levels: "
            f"{[r.levelname for r in caplog.records]}"
        )
        assert any(r.exc_info is not None for r in errors), (
            "expected exc_info to be set on the ERROR record"
        )
        assert any("test_plugin" in r.getMessage() for r in errors), (
            "expected plugin name in log message"
        )

    def test_caps_at_50(self):
        loop = _make_loop()
        for i in range(60):
            loop._record_skipped_plugin("p", ValueError(f"e{i}"))
        assert len(loop.diagnostics["skipped"]) == 50, (
            "diagnostics['skipped'] must be capped at 50 entries"
        )

    @pytest.mark.parametrize(
        "plugin_name",
        ["fallback_chain_filter", "compact_turn", "stop_hooks", "reflexion_apply"],
    )
    def test_entries_have_required_fields(self, plugin_name):
        loop = _make_loop()
        loop._record_skipped_plugin(plugin_name, RuntimeError("oops"))
        entries = loop.diagnostics["skipped"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["plugin"] == plugin_name
        assert entry["error"] == "oops"
        assert entry["type"] == "RuntimeError"

    def test_no_warning_or_debug_level_for_quiet_sites(self, caplog):
        loop = _make_loop()
        with caplog.at_level(logging.DEBUG, logger="butler.core.agent_loop"):
            loop._record_skipped_plugin("compact_turn", ValueError("x"))
        levels = {r.levelno for r in caplog.records}
        assert logging.WARNING not in levels, (
            f"plugin skip must not log at WARNING, got: "
            f"{[r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]}"
        )
        assert logging.DEBUG not in levels, (
            f"plugin skip must not log at DEBUG (silently drops in production), got: "
            f"{[r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]}"
        )


class TestAgentLoopSkippedIntegration:
    """Force each quiet site to raise, verify it lands in ``diagnostics['skipped']``."""

    def test_fallback_chain_filter_skip_records_to_diagnostics(self, monkeypatch):
        from butler.transport import provider_health

        def boom(_chain):
            raise RuntimeError("filter boom")

        monkeypatch.setattr(provider_health, "filter_fallback_chain", boom)

        loop = _make_loop()
        entries = loop.diagnostics.get("skipped", [])
        assert any(
            e["plugin"] == "fallback_chain_filter" and e["type"] == "RuntimeError"
            for e in entries
        ), f"expected fallback_chain_filter entry, got: {entries!r}"

    def test_compact_turn_skip_records_to_diagnostics(
        self, monkeypatch, mock_llm_client,
    ):
        from butler.core import agent_loop as agent_loop_module

        def boom_compact(loop, state):
            raise RuntimeError("compact boom")

        monkeypatch.setattr(
            agent_loop_module, "_phase_maybe_compact_turn", boom_compact,
        )

        loop = AgentLoop(mock_llm_client, config=LoopConfig(stream=False))
        loop.run("hello")
        entries = loop.diagnostics.get("skipped", [])
        assert any(
            e["plugin"] == "compact_turn" and e["type"] == "RuntimeError"
            for e in entries
        ), f"expected compact_turn entry, got: {entries!r}"

    def test_stop_hooks_skip_records_to_diagnostics(self, monkeypatch):
        from butler.hooks import runner

        def boom(*a, **kw):
            raise RuntimeError("stop hook boom")

        monkeypatch.setattr(runner, "run_stop_hooks", boom)

        loop = _make_loop()
        result = loop._maybe_stop_hook_continue(
            steer_session="default",
            iteration=1,
            start_time=0.0,
            final_text="hello",
        )
        assert result is False
        entries = loop.diagnostics.get("skipped", [])
        assert any(
            e["plugin"] == "stop_hooks" and e["type"] == "RuntimeError"
            for e in entries
        ), f"expected stop_hooks entry, got: {entries!r}"

    def test_reflexion_apply_skip_records_to_diagnostics(self, monkeypatch):
        from butler.core import reflexion_ephemeral

        def boom(*a, **kw):
            raise RuntimeError("reflexion boom")

        monkeypatch.setattr(reflexion_ephemeral, "maybe_apply_reflexion", boom)

        loop = _make_loop()
        # Precondition: guardrails exist and have a non-empty failure count
        if loop._guardrails is not None:
            loop._guardrails._same_tool_failure_counts = {"some_tool": 3}

        from butler.transport.types import NormalizedResponse

        resp = NormalizedResponse(content="", tool_calls=[], usage=None)
        loop._process_tool_calls(resp)
        entries = loop.diagnostics.get("skipped", [])
        assert any(
            e["plugin"] == "reflexion_apply" and e["type"] == "RuntimeError"
            for e in entries
        ), f"expected reflexion_apply entry, got: {entries!r}"
