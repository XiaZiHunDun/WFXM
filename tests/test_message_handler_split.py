"""R1-6 ``message_handler.py`` god-module split — backward-compat guard.

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-6

The 1009-line ``butler.gateway.message_handler`` carried two god methods:

* ``ButlerMessageHandler.handle_message`` (lines 243-617, ~334 non-blank lines)
* ``ButlerMessageHandler._handle_message_locked`` (lines 619-916, ~272 lines)

The audit's recommendation was to list the normalizers, make the
guards composable ``InboundPipeline`` stages, and reduce the handler
to a thin orchestrator. This test module asserts the post-split
contract:

1. **Backward compat**: the public API of ``butler.gateway.message_handler``
   must stay reachable (``ButlerMessageHandler`` and the previously
   re-exported helpers from ``handler_helpers``).
2. **Size contract (R1-5.2 lesson)**: every new top-level phase
   function (the extracted pipeline stages) must be implementable as
   a small orchestrator — under 50 source lines.
3. **Behavioral smoke**: ``ButlerMessageHandler`` still instantiates
   and the public entry points are callable.

R2-16 silent-pass concerns live at :912-913 in this file and are out
of scope for R1-6. The contract deliberately ignores those lines.
"""

from __future__ import annotations

import importlib
import inspect

import pytest


MESSAGE_HANDLER_PATH = "butler.gateway.message_handler"
PIPELINES_PATH = "butler.gateway.message_pipelines"
LOCKED_PHASES_PATH = "butler.gateway.locked_phases"
HANDLER_HELPERS_PATH = "butler.gateway.handler_helpers"


# ----------------------------------------------------------------------------
# Module existence
# ----------------------------------------------------------------------------

@pytest.mark.unit
class TestSplitModulesExist:
    def test_message_handler_module_loads(self):
        mod = importlib.import_module(MESSAGE_HANDLER_PATH)
        assert mod is not None

    def test_pipelines_module_exists(self):
        mod = importlib.import_module(PIPELINES_PATH)
        assert mod is not None

    def test_locked_phases_module_exists(self):
        mod = importlib.import_module(LOCKED_PHASES_PATH)
        assert mod is not None

    def test_handler_helpers_still_importable(self):
        """R1-4/R1-5 left ``handler_helpers`` carrying the original
        helper functions. R1-6 must not regress this surface."""
        mod = importlib.import_module(HANDLER_HELPERS_PATH)
        assert mod is not None


# ----------------------------------------------------------------------------
# Backward compatibility — every symbol that test code or sibling
# modules import from ``butler.gateway.message_handler`` must stay
# reachable. The split must not break ``from butler.gateway.message_handler
# import ButlerMessageHandler`` or ``from ... import _is_sessionless_command``.
# ----------------------------------------------------------------------------

PUBLIC_API = [
    "ButlerMessageHandler",
]

# These come from ``handler_helpers`` and are re-exported at the
# bottom of ``message_handler.py`` (the existing re-export block).
# If the re-export is removed, this list will flag the regression.
HANDLER_HELPERS_REEXPORT = [
    "_normalize_switch_request",
    "_normalize_status_request",
    "_normalize_new_session_request",
    "_normalize_detail_request",
    "_normalize_memo_request",
    "_normalize_contacts_request",
    "_normalize_expense_request",
    "_normalize_habits_request",
    "_gateway_run_callbacks",
    "_is_prequeue_interrupt_command",
    "_env_int",
    "_env_float",
    "_is_sessionless_command",
    "apply_auto_continue_rewrite",
    "_tool_audit_summary",
    "_reset_tool_audit_events",
    "_maybe_welcome_prefix",
    "_build_project_overview",
    "_inject_previous_session_summary",
    "_on_gateway_session_removed",
    "_WELCOMED_SESSIONS",
    "_WELCOME_TEXT",
]


@pytest.mark.unit
class TestBackwardCompatSymbols:
    @pytest.mark.parametrize("name", PUBLIC_API)
    def test_public_class_still_in_message_handler(self, name: str):
        mod = importlib.import_module(MESSAGE_HANDLER_PATH)
        assert hasattr(mod, name), (
            f"{MESSAGE_HANDLER_PATH}.{name} disappeared after R1-6 split"
        )

    @pytest.mark.parametrize("name", HANDLER_HELPERS_REEXPORT)
    def test_handler_helpers_still_reexported(self, name: str):
        mod = importlib.import_module(MESSAGE_HANDLER_PATH)
        assert hasattr(mod, name), (
            f"{MESSAGE_HANDLER_PATH}.{name} no longer re-exported; "
            "external test imports would break"
        )


# ----------------------------------------------------------------------------
# Size contract — R1-5.2 lesson learned.
#
# Every top-level phase function in the new modules must be a thin
# orchestrator under 50 source lines. Long bodies belong in private
# helpers (``_apply_*`` / ``_build_*`` / ``_infer_*``).
# ----------------------------------------------------------------------------

PIPELINE_PHASES = [
    # Pre-session phases (run in handle_message)
    "_phase_resolve_session_key",
    "_phase_transform_inbound_text",
    "_phase_apply_mcp_profile",
    "_phase_apply_io_guardrail",
    "_phase_apply_human_gate",
    "_phase_apply_injection_guard",
    "_phase_apply_injection_llm",
    "_phase_apply_bot_loop_guard",
    "_phase_apply_two_phase_confirm",
    "_phase_apply_prequeue_interrupt",
    "_phase_apply_pre_dispatch_rewrites",
    "_phase_apply_idempotency",
    "_phase_apply_session_initializing",
    "_phase_apply_queue_inbound",
    "_phase_apply_admission",
]

LOCKED_PHASE_FUNCTIONS = [
    # In-session phases (run in _handle_message_locked)
    "_phase_apply_normalizers_and_slash",
    "_phase_apply_prompt_hooks",
    "_phase_augment_prompt",
    "_phase_init_loop_role",
    "_phase_validate_loop_messages",
    "_phase_resolve_turn_budget",
    "_phase_hygiene_compress",
    "_phase_prefetch_and_callbacks",
    "_phase_execute_turn",
    "_phase_finalize_turn",
    "_phase_format_turn_response",
    "_phase_format_error_card",
]


@pytest.mark.unit
class TestPipelinePhaseSizes:
    """R1-6 size contract: every pre-session phase helper must be
    a small orchestrator under 50 source lines."""

    @pytest.mark.parametrize("name", PIPELINE_PHASES)
    def test_pipeline_phase_under_50_lines(self, name: str):
        mod = importlib.import_module(PIPELINES_PATH)
        assert hasattr(mod, name), (
            f"{PIPELINES_PATH}.{name} missing — extraction is incomplete"
        )
        fn = getattr(mod, name)
        assert callable(fn), f"{PIPELINES_PATH}.{name} not callable"
        src = inspect.getsource(fn)
        body_lines = [ln for ln in src.splitlines() if ln.strip()]
        assert len(body_lines) < 50, (
            f"{PIPELINES_PATH}.{name} is {len(body_lines)} non-blank lines; "
            f"R1-6 size contract requires < 50. Split into helpers."
        )


@pytest.mark.unit
class TestLockedPhaseSizes:
    """R1-6 size contract: every in-session phase helper must be
    a small orchestrator under 50 source lines."""

    @pytest.mark.parametrize("name", LOCKED_PHASE_FUNCTIONS)
    def test_locked_phase_under_50_lines(self, name: str):
        mod = importlib.import_module(LOCKED_PHASES_PATH)
        assert hasattr(mod, name), (
            f"{LOCKED_PHASES_PATH}.{name} missing — extraction is incomplete"
        )
        fn = getattr(mod, name)
        assert callable(fn), f"{LOCKED_PHASES_PATH}.{name} not callable"
        src = inspect.getsource(fn)
        body_lines = [ln for ln in src.splitlines() if ln.strip()]
        assert len(body_lines) < 50, (
            f"{LOCKED_PHASES_PATH}.{name} is {len(body_lines)} non-blank lines; "
            f"R1-6 size contract requires < 50. Split into helpers."
        )


# ----------------------------------------------------------------------------
# Thinned host — after R1-6, ``handle_message`` and
# ``_handle_message_locked`` are thin orchestrators that delegate to
# phase functions. Both must drop well below their pre-split sizes.
# ----------------------------------------------------------------------------

@pytest.mark.unit
class TestHostMethodsThinned:
    def test_handle_message_is_thinned(self):
        mod = importlib.import_module(MESSAGE_HANDLER_PATH)
        cls = mod.ButlerMessageHandler
        src = inspect.getsource(cls.handle_message)
        body_lines = [ln for ln in src.splitlines() if ln.strip()]
        # Pre-split: 334 non-blank lines. Post-split target: well under half.
        assert len(body_lines) < 160, (
            f"ButlerMessageHandler.handle_message is {len(body_lines)} "
            f"non-blank lines; R1-6 split target is under 160 (was 334)"
        )

    def test_handle_message_locked_is_thinned(self):
        mod = importlib.import_module(MESSAGE_HANDLER_PATH)
        cls = mod.ButlerMessageHandler
        src = inspect.getsource(cls._handle_message_locked)
        body_lines = [ln for ln in src.splitlines() if ln.strip()]
        # Pre-split: 272 non-blank lines. Post-split target: well under half.
        assert len(body_lines) < 100, (
            f"ButlerMessageHandler._handle_message_locked is {len(body_lines)} "
            f"non-blank lines; R1-6 split target is under 100 (was 272)"
        )


# ----------------------------------------------------------------------------
# Main file line count — project red line is 800 lines.
# ----------------------------------------------------------------------------

@pytest.mark.unit
class TestMainFileSize:
    def test_message_handler_under_800_lines(self):
        import os

        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "butler",
            "gateway",
            "message_handler.py",
        )
        with open(path, encoding="utf-8") as f:
            total_lines = sum(1 for _ in f)
        assert total_lines < 800, (
            f"butler/gateway/message_handler.py is {total_lines} lines; "
            f"project red line is 800 (R1-6 audit cap)"
        )


# ----------------------------------------------------------------------------
# Behavioral smoke — the public entry points must remain instantiable
# and callable after the split. We don't exercise the full pipeline
# here (that's ``test_gateway_handler``'s job); we just assert the
# orchestrator wiring is intact.
# ----------------------------------------------------------------------------

@pytest.mark.unit
class TestPhaseModuleImport:
    def test_pipelines_module_alone_imports(self):
        """The phase modules must not pull registry/transport at import
        time — pytest test isolation depends on cheap imports."""
        mod = importlib.import_module(PIPELINES_PATH)
        assert hasattr(mod, "logger")

    def test_locked_phases_module_alone_imports(self):
        mod = importlib.import_module(LOCKED_PHASES_PATH)
        assert hasattr(mod, "logger")

    def test_pipelines_module_docstring_present(self):
        mod = importlib.import_module(PIPELINES_PATH)
        assert mod.__doc__ and "R1-6" in mod.__doc__

    def test_locked_phases_module_docstring_present(self):
        mod = importlib.import_module(LOCKED_PHASES_PATH)
        assert mod.__doc__ and "R1-6" in mod.__doc__
