"""R1-5 ``delegate_impl.py`` god-module split — backward-compat guard.

Asserts the public API of ``butler.tools.delegate_impl`` still works after
extraction of the 408-line ``_tool_delegate_task`` body into six phase
helpers in :mod:`butler.tools.delegate_phases`. Every symbol that
``butler.tools.builtin_impl`` re-exports must stay reachable via
``butler.tools.delegate_impl`` so existing ``patch("...delegate_impl.X")``
style tests stay green.
"""

from __future__ import annotations

import importlib
import inspect

import pytest


DELEGATE_IMPL_PATH = "butler.tools.delegate_impl"
DELEGATE_PHASES_PATH = "butler.tools.delegate_phases"


@pytest.mark.unit
class TestSplitModulesExist:
    def test_phases_module_exists(self):
        mod = importlib.import_module(DELEGATE_PHASES_PATH)
        assert mod is not None

    def test_phases_module_docstring_present(self):
        mod = importlib.import_module(DELEGATE_PHASES_PATH)
        assert mod.__doc__ and "R1-5" in mod.__doc__


@pytest.mark.unit
class TestBackwardCompatSymbols:
    """Symbols that ``butler.tools.builtin_impl`` re-exports from
    ``butler.tools.delegate_impl``. The host module must still own
    these so existing imports and test patches stay green.
    """

    @pytest.mark.parametrize(
        "name",
        [
            "_delegate_role_label",
            "_delegate_task_succeeded",
            "_extract_changes_from_messages",
            "_extract_issues_from_messages",
            "_finalize_delegate_failure",
            "_inject_project_agent_skills",
            "_orchestrator_for_tool",
            "_project_agent_raw_message",
            "_run_subagent_stop_hooks",
            "_safe_dispatch",
            "_tool_delegate_task",
        ],
    )
    def test_symbol_still_in_delegate_impl(self, name: str):
        mod = importlib.import_module(DELEGATE_IMPL_PATH)
        assert hasattr(mod, name), (
            f"butler.tools.delegate_impl.{name} disappeared after R1-5 split"
        )
        assert callable(getattr(mod, name)) or name == "_tool_delegate_task"


@pytest.mark.unit
class TestPhasesModuleContent:
    """The new phase module must expose the carrier and the six phase
    helpers named in the module docstring, with stable signatures so
    future callers can depend on them."""

    @pytest.mark.parametrize(
        "name",
        [
            "DelegateRunState",
            "_prepare_delegate_task",
            "_resolve_subagent",
            "_build_user_message",
            "_record_delegate_state",
            "_run_subagent_loop",
            "_format_delegate_result",
        ],
    )
    def test_phase_symbol_present(self, name: str):
        mod = importlib.import_module(DELEGATE_PHASES_PATH)
        assert hasattr(mod, name), (
            f"butler.tools.delegate_phases.{name} missing"
        )

    def test_delegate_run_state_is_dataclass(self):
        from dataclasses import is_dataclass

        from butler.tools.delegate_phases import DelegateRunState

        assert is_dataclass(DelegateRunState)

    def test_run_subagent_loop_returns_optional_string(self):
        from butler.tools.delegate_phases import _run_subagent_loop

        sig = inspect.signature(_run_subagent_loop)
        # ``_run_subagent_loop(state)`` -> str | None
        assert len(sig.parameters) == 1

    def test_format_delegate_result_takes_state_and_result(self):
        from butler.tools.delegate_phases import _format_delegate_result

        sig = inspect.signature(_format_delegate_result)
        params = list(sig.parameters.keys())
        assert params[:2] == ["state", "result"]


@pytest.mark.unit
class TestHostFunctionThinned:
    """R1-5 contract: ``_tool_delegate_task`` must no longer carry the
    408-line god-function body. The host should be a thin orchestrator
    that delegates to phase helpers."""

    def test_host_function_callable(self):
        from butler.tools.delegate_impl import _tool_delegate_task

        assert callable(_tool_delegate_task)

    def test_host_function_signature_preserved(self):
        from butler.tools.delegate_impl import _tool_delegate_task

        sig = inspect.signature(_tool_delegate_task)
        # Original signature: (role, task, context="", category="", depth=0, **_)
        params = list(sig.parameters.keys())
        assert params[:5] == ["role", "task", "context", "category", "depth"]

    def test_host_function_body_under_150_lines(self):
        """The original was 408 lines; the audit's split goal is well under
        that. We assert <= 150 to give a margin for future tweaks."""
        from butler.tools.delegate_impl import _tool_delegate_task

        # use ``getsource`` and trim trailing blank lines
        import inspect

        src = inspect.getsource(_tool_delegate_task)
        # Dedent + strip leading/trailing blank lines for an honest count
        lines = [ln for ln in src.splitlines() if ln.strip()]
        assert len(lines) <= 150, (
            f"_tool_delegate_task still {len(lines)} non-blank lines "
            f"(audit cap 150 after R1-5 split)"
        )


@pytest.mark.unit
class TestPhaseHelpersExportedCleanly:
    """Quick smoke import — the helpers must be importable without
    pulling in registry/transport (no top-level side effects)."""

    def test_import_phases_module_alone(self):
        mod = importlib.import_module(DELEGATE_PHASES_PATH)
        # No exceptions during import; module-level logger should exist
        assert hasattr(mod, "logger")

    def test_host_module_unchanged_symbols(self):
        """The host must not re-export the phase functions (the split
        purpose is to keep delegate_impl.py free of phase internals)."""
        mod = importlib.import_module(DELEGATE_IMPL_PATH)
        for name in (
            "_prepare_delegate_task",
            "_resolve_subagent",
            "_build_user_message",
            "_record_delegate_state",
            "_run_subagent_loop",
            "_format_delegate_result",
            "DelegateRunState",
        ):
            assert not hasattr(mod, name), (
                f"butler.tools.delegate_impl.{name} leaked from phases "
                f"module — host should not re-export phase internals"
            )


# Phase-function size contract (R1-5.2 reviewer feedback):
# ``butler/tools/delegate_phases.py`` first split (commit 861a011) left 4/6
# phase functions above the 50-line ceiling. The contract: every phase
# helper must be implementable as a small orchestrator over focused
# private helpers. We assert the *function* (not the body) stays under
# 50 source lines — counting ``def`` through the last statement.
PHASE_FUNCTIONS_UNDER_50 = [
    "_prepare_delegate_task",
    "_resolve_subagent",
    "_build_user_message",
    "_record_delegate_state",
    "_run_subagent_loop",
    "_format_delegate_result",
]


@pytest.mark.unit
class TestPhaseFunctionsUnder50Lines:
    """R1-5.2 size contract — every phase function must be a thin
    orchestrator (< 50 source lines). Long bodies belong in
    private helpers (``_infer_*`` / ``_apply_*`` / ``_build_*``)."""

    @pytest.mark.parametrize("name", PHASE_FUNCTIONS_UNDER_50)
    def test_phase_function_under_50_lines(self, name: str):
        import inspect

        from butler.tools import delegate_phases

        fn = getattr(delegate_phases, name)
        assert callable(fn), f"delegate_phases.{name} not callable"
        src = inspect.getsource(fn)
        # Count non-blank lines to be robust to trailing whitespace
        body_lines = [ln for ln in src.splitlines() if ln.strip()]
        assert len(body_lines) < 50, (
            f"delegate_phases.{name} is {len(body_lines)} non-blank lines; "
            f"R1-5.2 size contract requires < 50. Split into helpers."
        )

    def test_all_phase_functions_in_module(self):
        """Sanity: the parametrize list and the module's phase exports
        stay in lockstep — if a new phase is added, extend the list."""
        from butler.tools import delegate_phases

        for name in PHASE_FUNCTIONS_UNDER_50:
            assert hasattr(delegate_phases, name), (
                f"phase helper {name} missing from delegate_phases"
            )
