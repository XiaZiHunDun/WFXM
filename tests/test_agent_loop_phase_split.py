"""R1-8 ``agent_loop.py`` god-module split — backward-compat guard.

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-8

The original ``AgentLoop._run_turn_body`` (337 lines, lines 250-587) was a
god method combining turn budget / callback / interrupt / token / ephemeral /
API / guardrail / tool batch / 压缩回退 — a 3.4x overrun of the 100-line
audit cap. The audit's recommended split was::

    _phase_init / _phase_call_llm / _phase_dispatch_tools / _phase_finalize
    # each segment within 80 lines

The project-wide rule from ``common/coding-style.md`` tightens the cap
to 50 lines. This test module asserts the post-split contract:

1. **Backward compat**: ``butler.core.agent_loop`` still exposes
   ``AgentLoop`` and the public ``_init_turn_state`` / ``_prepare_user_message``
   / ``_run_turn_body`` entry points used by callers and tests.
2. **Module layout**: a new ``butler/core/agent_loop_phases.py`` carries
   the phase helpers, mirroring the R1-5.2 / R1-6 pattern.
3. **Size contract (R1-5.2 lesson)**: every top-level phase function must
   be a thin orchestrator under 50 source lines. Long bodies belong in
   private helpers (``_record_*`` / _mark_* / _try_* / _store_* / _build_*``).
4. **Thinned host**: ``_run_turn_body`` (the orchestrator) and
   ``_prepare_user_message`` (the user-message orchestrator) must each
   drop well below their pre-split sizes (337L and 53L respectively).
5. **R1-2 touchpoint protection**: lines 27 (import) and 143
   (merge_loop_callbacks usage in ``run()``) of ``agent_loop.py`` must
   remain byte-identical to their pre-R1-8 state.
6. **Behavioral smoke**: instantiating ``AgentLoop`` and calling
   ``_run_turn_body`` exercises the 4 phases in the documented order.
"""

from __future__ import annotations

import importlib
import inspect

import pytest


AGENT_LOOP_PATH = "butler.core.agent_loop"
PHASES_PATH = "butler.core.agent_loop_phases"


# ----------------------------------------------------------------------------
# Module existence
# ----------------------------------------------------------------------------

@pytest.mark.unit
class TestSplitModulesExist:
    def test_agent_loop_module_loads(self):
        mod = importlib.import_module(AGENT_LOOP_PATH)
        assert mod is not None

    def test_phases_module_exists(self):
        mod = importlib.import_module(PHASES_PATH)
        assert mod is not None

    def test_phases_module_docstring_mentions_r18(self):
        mod = importlib.import_module(PHASES_PATH)
        assert mod.__doc__ and "R1-8" in mod.__doc__, (
            f"{PHASES_PATH} docstring must reference R1-8 audit source"
        )

    def test_phases_module_logger(self):
        mod = importlib.import_module(PHASES_PATH)
        assert hasattr(mod, "logger"), (
            f"{PHASES_PATH} must define module-level logger"
        )


# ----------------------------------------------------------------------------
# Public API — symbols the rest of the codebase (and tests) still need.
# ----------------------------------------------------------------------------

AGENT_LOOP_PUBLIC_API = [
    "AgentLoop",
    "LoopCallbacks",
    "LoopConfig",
    "LoopResult",
    "LoopStatus",
    "LoopTransitionReason",
]


@pytest.mark.unit
class TestBackwardCompatSymbols:
    @pytest.mark.parametrize("name", AGENT_LOOP_PUBLIC_API)
    def test_symbol_still_in_agent_loop(self, name: str):
        mod = importlib.import_module(AGENT_LOOP_PATH)
        assert hasattr(mod, name), (
            f"{AGENT_LOOP_PATH}.{name} disappeared after R1-8 split"
        )

    @pytest.mark.parametrize(
        "name", ["_init_turn_state", "_prepare_user_message", "_run_turn_body"],
    )
    def test_class_method_still_on_agent_loop(self, name: str):
        """The original methods must remain as methods on the AgentLoop class.

        The R1-8 split reduces their bodies to thin orchestrators; it does
        not remove them. Other modules (and tests) still call
        ``loop._prepare_user_message`` and ``loop._run_turn_body`` by name.
        """
        mod = importlib.import_module(AGENT_LOOP_PATH)
        cls = mod.AgentLoop
        assert hasattr(cls, name), (
            f"AgentLoop.{name} disappeared after R1-8 split"
        )
        assert callable(getattr(cls, name)), (
            f"AgentLoop.{name} must remain callable"
        )


# ----------------------------------------------------------------------------
# Phase symbols — every audit-named phase + user-message sub-phase.
# ----------------------------------------------------------------------------

PHASE_FUNCTIONS = [
    # 4 audit-suggested turn phases
    "_phase_init",
    "_phase_call_llm",
    "_phase_dispatch_tools",
    "_phase_finalize",
    # 2 user-message sub-phases (wider contract, R1-5.2 lesson)
    "_phase_resolve_user_text",
    "_phase_enrich_user_text",
]


@pytest.mark.unit
class TestPhaseSymbolsPresent:
    @pytest.mark.parametrize("name", PHASE_FUNCTIONS)
    def test_phase_symbol_present(self, name: str):
        mod = importlib.import_module(PHASES_PATH)
        assert hasattr(mod, name), (
            f"{PHASES_PATH}.{name} missing — extraction is incomplete"
        )
        assert callable(getattr(mod, name)), (
            f"{PHASES_PATH}.{name} must be callable"
        )


# ----------------------------------------------------------------------------
# Size contract — R1-5.2 lesson learned. Every phase function must be a
# thin orchestrator under 50 source lines.
# ----------------------------------------------------------------------------

@pytest.mark.unit
class TestPhaseFunctionsUnder50Lines:
    """R1-8 size contract: every phase helper must be < 50 source lines."""

    @pytest.mark.parametrize("name", PHASE_FUNCTIONS)
    def test_phase_function_under_50_lines(self, name: str):
        mod = importlib.import_module(PHASES_PATH)
        assert hasattr(mod, name), (
            f"{PHASES_PATH}.{name} missing"
        )
        fn = getattr(mod, name)
        assert callable(fn), f"{PHASES_PATH}.{name} not callable"
        src = inspect.getsource(fn)
        body_lines = [ln for ln in src.splitlines() if ln.strip()]
        assert len(body_lines) < 50, (
            f"{PHASES_PATH}.{name} is {len(body_lines)} non-blank lines; "
            f"R1-8 size contract requires < 50. Split into helpers."
        )


# ----------------------------------------------------------------------------
# Thinned host — after R1-8, ``_run_turn_body`` and ``_prepare_user_message``
# are thin orchestrators that delegate to phase functions.
# ----------------------------------------------------------------------------

@pytest.mark.unit
class TestHostMethodsThinned:
    def test_run_turn_body_is_thinned(self):
        mod = importlib.import_module(AGENT_LOOP_PATH)
        cls = mod.AgentLoop
        src = inspect.getsource(cls._run_turn_body)
        body_lines = [ln for ln in src.splitlines() if ln.strip()]
        # Pre-split: 337 non-blank lines. Post-split target: < 50.
        assert len(body_lines) < 50, (
            f"AgentLoop._run_turn_body is {body_lines} non-blank lines; "
            f"R1-8 split target is < 50 (was 337)"
        )

    def test_prepare_user_message_is_thinned(self):
        mod = importlib.import_module(AGENT_LOOP_PATH)
        cls = mod.AgentLoop
        src = inspect.getsource(cls._prepare_user_message)
        body_lines = [ln for ln in src.splitlines() if ln.strip()]
        # Pre-split: 53 non-blank lines. Post-split target: < 50.
        assert len(body_lines) < 50, (
            f"AgentLoop._prepare_user_message is {body_lines} non-blank lines; "
            f"wider-contract split target is < 50 (was 53)"
        )


# ----------------------------------------------------------------------------
# AST guard — every method on ``AgentLoop`` must be ≤ 50 lines.
# ----------------------------------------------------------------------------

import ast as _ast
import pathlib as _pathlib


@pytest.mark.unit
class TestAgentLoopAllMethodsUnder50Lines:
    """Project-wide rule from common/coding-style.md: every method ≤ 50 lines.

    Catches the next god-method refactor by walking the AST and asserting
    each function/method body is below the cap.
    """

    def test_no_method_exceeds_50_lines(self):
        src_path = _pathlib.Path(importlib.import_module(AGENT_LOOP_PATH).__file__)
        text = src_path.read_text(encoding="utf-8")
        tree = _ast.parse(text)
        offenders: list[tuple[str, int, int]] = []
        for node in _ast.walk(tree):
            if isinstance(node, (ast_function := _ast.FunctionDef, _ast.AsyncFunctionDef)):
                # Count non-blank, non-pure-docstring lines as body size
                end = getattr(node, "end_lineno", None) or node.lineno
                # Use end_lineno minus start
                src_lines = text.splitlines()
                body = src_lines[node.lineno - 1:end]
                non_blank = [ln for ln in body if ln.strip()]
                if len(non_blank) > 50:
                    offenders.append((node.name, node.lineno, len(non_blank)))
        assert not offenders, (
            f"agent_loop.py methods over 50 lines: " + ", ".join(
                f"{n}@{ln}={sz}L" for n, ln, sz in offenders
            )
        )


# ----------------------------------------------------------------------------
# R1-2 touchpoint protection — line 27 import and line 143 merge_loop_callbacks
# must remain byte-identical to their pre-R1-8 state.
# ----------------------------------------------------------------------------

@pytest.mark.unit
class TestR12TouchpointProtection:
    """R1-2 fix left two touchpoints in agent_loop.py that R1-8 must not disturb:

    * Line 27: ``from butler.core.interrupt import ...`` (R1-2 part 2)
    * The ``from butler.core.loop_callbacks_merge import merge_loop_callbacks``
      import inside ``run()`` (R1-2 part 1; the function was relocated from
      gateway to core)

    We assert the source text for both touchpoints stays exactly as-is.
    Line 27 must remain at line 27 (we add new imports AFTER the existing
    block, never before it). The merge_loop_callbacks import may shift to
    a different line number, but its line content must be unchanged.
    """

    def test_line_27_interrupt_import_intact(self):
        src_path = _pathlib.Path(importlib.import_module(AGENT_LOOP_PATH).__file__)
        text = src_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert lines[26] == (
            "from butler.core.interrupt import clear_interrupt, is_interrupted, set_interrupt"
        ), (
            f"agent_loop.py:27 changed; R1-2 part 2 import was disturbed. "
            f"Got: {lines[26]!r}"
        )

    def test_merge_loop_callbacks_import_intact(self):
        """The R1-2 part 1 import line content must be byte-identical.

        The line number may shift because R1-8 legitimately adds new imports
        to the module top — but the line content (indentation, source
        module, imported symbol) must stay exactly as the R1-2 fix left it.
        """
        src_path = _pathlib.Path(importlib.import_module(AGENT_LOOP_PATH).__file__)
        text = src_path.read_text(encoding="utf-8")
        expected = (
            "            from butler.core.loop_callbacks_merge import "
            "merge_loop_callbacks"
        )
        assert expected in text, (
            f"R1-2 part 1 import line `from butler.core.loop_callbacks_merge "
            f"import merge_loop_callbacks` was disturbed or removed by R1-8."
        )


# ----------------------------------------------------------------------------
# Behavioral smoke — ``_run_turn_body`` must call the 4 phases in order
# (after _phase_init), then return a LoopResult. We patch each phase
# helper to a recording stub and assert the recorded call order.
# ----------------------------------------------------------------------------

@pytest.mark.unit
class TestRunTurnBodyCallsPhasesInOrder:
    """Behavioral smoke: the 4 audit phases execute in the documented order
    when ``_run_turn_body`` runs a single text-response turn.
    """

    def test_text_turn_calls_phases_init_then_call_llm_then_finalize(
        self, mock_llm_client, mock_llm_response
    ):
        # Patches must target the *imported* names in agent_loop, not
        # the source module (otherwise agent_loop still holds the
        # original function objects captured at import time).
        import butler.core.agent_loop as agent_loop_mod
        from butler.core import agent_loop_phases as phases
        from butler.core.agent_loop import AgentLoop, LoopConfig, LoopStatus

        mock_llm_client.complete.return_value = mock_llm_response(content="hello")
        loop = AgentLoop(mock_llm_client, config=LoopConfig(stream=False))

        calls: list[str] = []
        original_init = agent_loop_mod._phase_init
        original_call = agent_loop_mod._phase_call_llm
        original_dispatch = agent_loop_mod._phase_dispatch_tools
        original_finalize = agent_loop_mod._phase_finalize

        def _record_init(loop_obj, user_message, steer_session, state):
            calls.append("_phase_init")
            return original_init(loop_obj, user_message, steer_session, state)

        def _record_call(loop_obj, state):
            calls.append("_phase_call_llm")
            return original_call(loop_obj, state)

        def _record_dispatch(loop_obj, response, state, start_time, steer_session):
            calls.append("_phase_dispatch_tools")
            return original_dispatch(loop_obj, response, state, start_time, steer_session)

        def _record_finalize(loop_obj, state, run_callbacks, steer_session, start_time):
            calls.append("_phase_finalize")
            return original_finalize(loop_obj, state, run_callbacks, steer_session, start_time)

        agent_loop_mod._phase_init = _record_init
        agent_loop_mod._phase_call_llm = _record_call
        agent_loop_mod._phase_dispatch_tools = _record_dispatch
        agent_loop_mod._phase_finalize = _record_finalize
        try:
            result = loop.run("hello")
        finally:
            agent_loop_mod._phase_init = original_init
            agent_loop_mod._phase_call_llm = original_call
            agent_loop_mod._phase_dispatch_tools = original_dispatch
            agent_loop_mod._phase_finalize = original_finalize

        assert result.status == LoopStatus.COMPLETED
        # init must be called first
        assert calls[0] == "_phase_init", (
            f"first call should be _phase_init, got {calls[0]}"
        )
        # finalize must be called last
        assert calls[-1] == "_phase_finalize", (
            f"last call should be _phase_finalize, got {calls[-1]}"
        )
        # call_llm + dispatch_tools must be interleaved (call_llm before
        # dispatch_tools for a single text-response iteration)
        assert "_phase_call_llm" in calls, "_phase_call_llm was not called"
        assert "_phase_dispatch_tools" in calls, (
            "_phase_dispatch_tools was not called for a text response"
        )
        # Order: init → call_llm → dispatch_tools → finalize
        idx_init = calls.index("_phase_init")
        idx_call = calls.index("_phase_call_llm")
        idx_disp = calls.index("_phase_dispatch_tools")
        idx_fin = calls.index("_phase_finalize")
        assert idx_init < idx_call < idx_disp < idx_fin, (
            f"phase call order is {calls}; expected init < call_llm < "
            f"dispatch_tools < finalize"
        )


# ----------------------------------------------------------------------------
# TurnBodyState carrier — phases must share mutable state via this carrier.
# ----------------------------------------------------------------------------

@pytest.mark.unit
class TestTurnBodyStateCarrier:
    def test_turn_body_state_is_dataclass(self):
        from dataclasses import is_dataclass

        from butler.core.agent_loop_phases import TurnBodyState

        assert is_dataclass(TurnBodyState), (
            "TurnBodyState must be a @dataclass to serve as a phase carrier"
        )

    def test_turn_body_state_has_expected_fields(self):
        from butler.core.agent_loop_phases import TurnBodyState

        field_names = {f.name for f in TurnBodyState.__dataclass_fields__.values()}
        for expected in (
            "original_config",
            "budget_state",
            "user_content",
            "turn_tools",
            "status",
            "transition",
            "iteration",
            "final_text",
            "final_reasoning",
        ):
            assert expected in field_names, (
                f"TurnBodyState missing field: {expected}"
            )
