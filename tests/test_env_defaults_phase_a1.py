"""Phase A1: env_defaults relocation — defaults unchanged at runtime."""

from __future__ import annotations

import os

import pytest

from butler.defaults import env_defaults as ed
from butler.core import context_budget, instruction_walkup, tool_prune_policy, turn_token_budget
from butler.gateway import completion_notify
from butler.transport import provider_health


@pytest.mark.unit
class TestEnvDefaultsPhaseA1:
    def test_context_budget_uses_defaults_when_unset(self, monkeypatch):
        for key in (
            "BUTLER_CONTEXT_OUTPUT_RESERVE",
            "BUTLER_CONTEXT_COMPACT_RESERVE",
            "BUTLER_CONTEXT_WARNING_BUFFER",
            "BUTLER_CONTEXT_ERROR_BUFFER",
            "BUTLER_CONTEXT_BLOCKING_BUFFER",
            "BUTLER_CONTEXT_COMPACT_MAX_FAILURES",
        ):
            monkeypatch.delenv(key, raising=False)
        assert context_budget.get_output_reserve_tokens() == ed.CONTEXT_OUTPUT_RESERVE
        th = context_budget.load_context_thresholds(128_000)
        assert th.max_consecutive_compact_failures == ed.CONTEXT_COMPACT_MAX_FAILURES

    def test_turn_budget_defaults(self, monkeypatch):
        monkeypatch.delenv("BUTLER_TURN_BUDGET_MIN_ITERATIONS", raising=False)
        monkeypatch.delenv("BUTLER_TURN_BUDGET_MAX_ITERATIONS", raising=False)
        monkeypatch.delenv("BUTLER_TURN_BUDGET_DEFAULT", raising=False)
        assert turn_token_budget.budget_to_max_iterations(500_000, base=10) <= ed.TURN_BUDGET_MAX_ITERATIONS

    def test_tool_prune_defaults(self, monkeypatch):
        monkeypatch.delenv("BUTLER_TOOL_PRUNE_KEEP_RECENT", raising=False)
        assert tool_prune_policy.keep_recent_tool_messages() == ed.TOOL_PRUNE_KEEP_RECENT
        assert tool_prune_policy.prune_limit_chars("default") == ed.TOOL_PRUNE_DEFAULT_CHARS

    def test_provider_circuit_defaults(self, monkeypatch):
        monkeypatch.delenv("BUTLER_PROVIDER_CIRCUIT_FAILURES", raising=False)
        monkeypatch.delenv("BUTLER_PROVIDER_CIRCUIT_OPEN_SECONDS", raising=False)
        assert provider_health._failure_threshold() == ed.PROVIDER_CIRCUIT_FAILURES
        assert provider_health._open_seconds() == ed.PROVIDER_CIRCUIT_OPEN_SECONDS

    def test_completion_notify_min_seconds(self, monkeypatch):
        monkeypatch.delenv("BUTLER_GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS", raising=False)
        assert completion_notify.min_elapsed_for_push() == ed.GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS

    def test_instruction_walkup_module_constants(self):
        assert ed.INSTRUCTION_WALKUP_MAX_CHARS == 4000
        assert ed.INSTRUCTION_WALKUP_MAX_FILES == 3

    def test_onboarding_default_string(self):
        assert ed.ONBOARDING_WELCOME_DEFAULT == "1"
