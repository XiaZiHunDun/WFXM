"""Integration tests for L4 Development Engine wiring into Butler Loop.

Validates:
  - Tool registration (I1)
  - Project tools allowlist for dev role (I2)
  - Dev engine prompt injection (I3)
  - DevState lifecycle in delegate flow (I4)
  - Post-edit hook recording (I5)
  - Env var readers (I6)
"""

from __future__ import annotations

import json
import os
import time
from unittest import mock

import pytest


# ── I1: Tool Registration ───────────────────────────────────────


class TestDevEngineToolRegistration:
    """Verify dev engine tools register into Butler registry."""

    def test_register_dev_engine_tools_populates_registry(self):
        """All 4 dev tools registered when engine enabled."""
        registered: dict[str, dict] = {}

        def fake_register(*, name, description, schema, handler, toolset="default"):
            registered[name] = {
                "description": description,
                "schema": schema,
                "handler": handler,
                "toolset": toolset,
            }

        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1"}):
            from butler.dev_engine.dev_tools import register_dev_engine_tools

            register_dev_engine_tools(fake_register)

        expected = {
            "dev_status",
            "dev_verify",
            "dev_rollback",
            "dev_search_symbols",
            "dev_metrics",
            "run_pytest",
        }
        assert expected == set(registered), f"Missing tools: {expected - set(registered)}"
        for name in expected:
            assert registered[name]["toolset"] == "dev_engine"

    def test_register_skipped_when_disabled(self):
        registered = {}

        def fake_register(*, name, **kw):
            registered[name] = kw

        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "0"}):
            from butler.dev_engine.dev_tools import register_dev_engine_tools

            register_dev_engine_tools(fake_register)

        assert len(registered) == 0

    def test_dev_status_handler_returns_json(self):
        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1"}):
            from butler.dev_engine.dev_tools import _active_states, _handler_dev_status
            from butler.dev_engine.dev_loop import create_dev_state

            _active_states["_default"] = create_dev_state("test task")
            try:
                result = _handler_dev_status()
                parsed = json.loads(result)
                assert parsed["phase"] == "PLAN"
                assert "iteration" in parsed
            finally:
                _active_states.pop("_default", None)

    def test_dev_search_symbols_tool_exists(self):
        """dev_search_symbols is a registered tool with required 'name' param."""
        registered = {}

        def fake_register(*, name, schema, **kw):
            registered[name] = schema

        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1"}):
            from butler.dev_engine.dev_tools import register_dev_engine_tools

            register_dev_engine_tools(fake_register)

        schema = registered["dev_search_symbols"]
        assert "name" in schema.get("required", [])


# ── I2: Project Tools Allowlist ─────────────────────────────────


class TestDevToolsAllowlist:
    """Verify dev_engine tools appear in allowlist for dev role."""

    def test_dev_extra_tools_constant(self):
        from butler.tools.project_tools import _DEV_EXTRA_TOOLS

        expected = {"dev_status", "dev_verify", "dev_rollback", "dev_search_symbols", "run_pytest"}
        assert expected == set(_DEV_EXTRA_TOOLS)

    def test_dev_role_includes_dev_tools_in_allowlist(self):
        """When role=dev and engine enabled, dev tools in allowed set."""
        from unittest.mock import MagicMock

        from butler.project.model import Project

        project = MagicMock(spec=Project)
        project.tools = ["read_file", "write_file", "patch", "terminal", "search_files"]
        project.tool_modes = {}

        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1"}):
            from butler.tools.project_tools import allowed_tool_names_for_project

            allowed = allowed_tool_names_for_project(project, role="dev")

        assert allowed is not None
        for tool in ["dev_status", "dev_verify", "dev_rollback", "dev_search_symbols"]:
            assert tool in allowed, f"{tool} not in dev allowlist"

    def test_dev_role_excludes_dev_tools_when_disabled(self):
        from unittest.mock import MagicMock

        from butler.project.model import Project

        project = MagicMock(spec=Project)
        project.tools = ["read_file", "write_file"]
        project.tool_modes = {}

        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "0"}):
            from butler.tools.project_tools import allowed_tool_names_for_project

            allowed = allowed_tool_names_for_project(project, role="dev")

        assert allowed is not None
        assert "dev_status" not in allowed


# ── I3: Dev Engine System Prompt ────────────────────────────────


class TestDevEnginePrompt:
    def test_dev_engine_prompt_file_exists(self):
        from pathlib import Path

        md = Path("butler/prompts/dev_engine_system.md")
        assert md.is_file(), "dev_engine_system.md not found"
        content = md.read_text(encoding="utf-8")
        assert "PLAN" in content
        assert "VERIFY" in content
        assert "dev_verify" in content
        assert "dev_rollback" in content

    def test_get_dev_agent_prompt_appends_engine(self):
        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1"}):
            import butler.agent_profiles as ap

            ap._DEV_ENGINE_APPENDIX = ""
            prompt = ap.get_dev_agent_prompt()
            assert "开发引擎" in prompt or "Development Engine" in prompt
            assert "dev_verify" in prompt

    def test_get_dev_agent_prompt_base_when_disabled(self):
        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "0"}):
            import butler.agent_profiles as ap

            ap._DEV_ENGINE_APPENDIX = ""
            prompt = ap.get_dev_agent_prompt()
            assert "dev_verify" not in prompt


# ── I4: DevState Lifecycle in Delegate ──────────────────────────


class TestDevStateDelegateLifecycle:
    def test_init_dev_engine_state_creates_state(self):
        from butler.tools.delegate_phases import DelegateRunState, _init_dev_engine_state

        state = DelegateRunState(role="dev", task="Fix bug in parser")
        state.child_session_key = "test::child::1"
        state.session_key = "test::parent"

        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1"}):
            from butler.dev_engine.dev_tools import _active_states

            _active_states.clear()
            _init_dev_engine_state(state)

            assert "test::child::1" in _active_states
            ds = _active_states["test::child::1"]
            assert ds.task_description == "Fix bug in parser"
            assert ds.phase.value == "PLAN"
            _active_states.clear()

    def test_init_registers_plugin_on_child_agent(self):
        from butler.core.loop_plugins import LoopPluginRegistry
        from butler.tools.delegate_phases import DelegateRunState, _init_dev_engine_state

        class _FakeAgent:
            def __init__(self):
                self._plugins = LoopPluginRegistry()

        state = DelegateRunState(role="dev", task="patch test_b9")
        state.child_session_key = "parent::child::9"
        state.agent = _FakeAgent()

        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1"}):
            from butler.dev_engine.dev_tools import _active_states

            _active_states.clear()
            _init_dev_engine_state(state)

            assert len(state.agent._plugins._after_tools_hooks) == 1
            assert len(state.agent._plugins._before_llm_hooks) == 1
            assert "parent::child::9" in _active_states
            _active_states.clear()

    def test_init_dev_engine_state_scoped_experience(self, tmp_path):
        from types import SimpleNamespace

        from butler.dev_engine.coding_knowledge import CodingExperience, ExperienceLibrary
        from butler.memory.memory_scope import infer_default_scope
        from butler.tools.delegate_phases import DelegateRunState, _init_dev_engine_state

        butler_home = tmp_path / "butler"
        butler_home.mkdir()
        xlib = ExperienceLibrary()
        xlib.add(
            CodingExperience(
                id="B9_EX_prod_lingwen_demo_add",
                title="lw",
                domain=["b9"],
                theorem_basis={"T01", "T03", "T04", "T10"},
                context="lingwen demo",
                pattern="p",
                benchmarks={"retrieval_keywords": "lingwen,demo,add"},
                scope=infer_default_scope(
                    exp_id="B9_EX_prod_lingwen_demo_add", domain=["b9"]
                ),
            ),
            skip_validation=True,
        )
        xlib.save_to_file(str(butler_home / "coding_experiences.json"))

        ws = tmp_path / "demo"
        ws.mkdir()
        project = SimpleNamespace(
            name="演示试点",
            workspace=ws,
            pack="",
            type="software",
        )
        state = DelegateRunState(
            role="dev",
            task="fix lingwen demo add operator",
            project=project,
        )
        state.child_session_key = "scope::child"
        state.session_key = "scope::parent"

        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1"}):
            with mock.patch(
                "butler.config.get_butler_home",
                return_value=str(butler_home),
            ):
                from butler.dev_engine.dev_tools import _active_states

                _active_states.clear()
                _init_dev_engine_state(state)
                ds = _active_states.get("scope::child")
                assert ds is not None
                assert ds.coding_knowledge.experience_id != "B9_EX_prod_lingwen_demo_add"
                _active_states.clear()

    def test_init_skipped_for_non_dev_role(self):
        from butler.tools.delegate_phases import DelegateRunState, _init_dev_engine_state

        state = DelegateRunState(role="content", task="Write article")
        state.child_session_key = "test::child::2"

        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1"}):
            from butler.dev_engine.dev_tools import _active_states

            _active_states.clear()
            _init_dev_engine_state(state)
            assert "test::child::2" not in _active_states

    def test_attach_dev_engine_summary_in_payload(self):
        from butler.tools.delegate_phases import (
            DelegateRunState,
            _attach_dev_engine_summary,
        )

        state = DelegateRunState(role="dev", task="Test task")
        state.child_session_key = "test::child::3"

        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1"}):
            from butler.dev_engine.dev_loop import create_dev_state
            from butler.dev_engine.dev_tools import _active_states

            ds = create_dev_state("Test task")
            ds.iteration = 5
            _active_states["test::child::3"] = ds

            payload: dict = {"success": True}
            _attach_dev_engine_summary(state, payload)

            assert "dev_engine" in payload
            assert payload["dev_engine"]["phase"] == "PLAN"
            assert payload["dev_engine"]["iterations"] == 5
            assert "test::child::3" not in _active_states


# ── I5: Post-Edit Hook ─────────────────────────────────────────


class TestPostEditHook:
    def test_post_edit_records_edit_in_dev_state(self):
        from butler.core.tool_batch import _dev_engine_post_edit
        from butler.dev_engine.dev_loop import create_dev_state
        from butler.dev_engine.dev_state import DevPhase
        from butler.dev_engine.dev_tools import _active_states

        ds = create_dev_state("test task")
        ds.phase = DevPhase.EDIT
        _active_states["_default"] = ds
        assert len(ds.edit_history) == 0

        args = {"path": "/tmp/test.py", "content": "x = 1"}
        result_json = json.dumps({"ok": True, "path": "/tmp/test.py"})
        with mock.patch(
            "butler.execution_context.get_current_session_key", return_value="_default"
        ), mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1", "BUTLER_DEV_AUTO_VERIFY": "0"}):
            _dev_engine_post_edit("write_file", args, result_json)

        assert len(ds.edit_history) == 1
        assert ds.edit_history[0].path == "/tmp/test.py"
        assert ds.edit_history[0].operation == "write"
        _active_states.clear()

    def test_post_edit_ignores_non_edit_tools(self):
        from butler.core.tool_batch import _dev_engine_post_edit

        _dev_engine_post_edit("read_file", {}, '{"ok": true}')
        _dev_engine_post_edit("search_files", {}, '{"ok": true}')
        _dev_engine_post_edit("terminal", {}, '{"ok": true}')

    def test_post_edit_ignores_error_results(self):
        from butler.core.tool_batch import _dev_engine_post_edit
        from butler.dev_engine.dev_loop import create_dev_state
        from butler.dev_engine.dev_state import DevPhase
        from butler.dev_engine.dev_tools import _active_states

        ds = create_dev_state("test")
        ds.phase = DevPhase.EDIT
        _active_states["_default"] = ds

        error_result = json.dumps({"error": "Permission denied"})
        with mock.patch(
            "butler.execution_context.get_current_session_key", return_value="_default"
        ), mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1"}):
            _dev_engine_post_edit("write_file", {"path": "/tmp/x.py"}, error_result)

        assert len(ds.edit_history) == 0
        _active_states.clear()

    def test_post_edit_no_crash_without_active_state(self):
        """No DevState in _active_states — hook is silent no-op."""
        from butler.core.tool_batch import _dev_engine_post_edit
        from butler.dev_engine.dev_tools import _active_states

        _active_states.clear()
        _dev_engine_post_edit("write_file", {"path": "/tmp/x.py"}, '{"ok": true, "path": "/tmp/x.py"}')


# ── I6: Environment Variable Readers ───────────────────────────


class TestEnvVarReaders:
    def test_dev_engine_enabled_defaults_true(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BUTLER_DEV_ENGINE", None)
            from butler.dev_engine.dev_tools import dev_engine_enabled

            assert dev_engine_enabled() is True

    def test_auto_verify_enabled(self):
        with mock.patch.dict(os.environ, {"BUTLER_DEV_AUTO_VERIFY": "0"}):
            from butler.dev_engine.dev_tools import auto_verify_enabled

            assert auto_verify_enabled() is False

    def test_rollback_enabled(self):
        with mock.patch.dict(os.environ, {"BUTLER_DEV_ROLLBACK_ENABLED": "0"}):
            from butler.dev_engine.dev_tools import rollback_enabled

            assert rollback_enabled() is False

    def test_diagnostics_inject_enabled(self):
        with mock.patch.dict(os.environ, {"BUTLER_DEV_DIAGNOSTICS_INJECT": "yes"}):
            from butler.dev_engine.dev_tools import diagnostics_inject_enabled

            assert diagnostics_inject_enabled() is True

    def test_rollback_handler_blocked_when_disabled(self):
        with mock.patch.dict(os.environ, {"BUTLER_DEV_ROLLBACK_ENABLED": "0"}):
            from butler.dev_engine.dev_tools import _handler_dev_rollback

            result = json.loads(_handler_dev_rollback(n=1))
            assert "error" in result


# ── G1: EditRecord snapshots + operation normalization ──────────


class TestEditRecordSnapshots:
    def test_post_edit_normalizes_op_name(self):
        """write_file → 'write', patch → 'patch', delete_file → 'delete'."""
        from butler.core.tool_batch import _OP_NAME_MAP

        assert _OP_NAME_MAP["write_file"] == "write"
        assert _OP_NAME_MAP["patch"] == "patch"
        assert _OP_NAME_MAP["delete_file"] == "delete"

    def test_post_edit_captures_patch_old_new(self):
        from butler.core.tool_batch import _dev_engine_post_edit
        from butler.dev_engine.dev_loop import create_dev_state
        from butler.dev_engine.dev_state import DevPhase
        from butler.dev_engine.dev_tools import _active_states

        ds = create_dev_state("test")
        ds.phase = DevPhase.EDIT
        _active_states["_default"] = ds

        args = {"path": "/tmp/test.py", "old_string": "foo", "new_string": "bar"}
        result = json.dumps({"success": True, "replacements": 1, "path": "/tmp/test.py"})
        with mock.patch(
            "butler.execution_context.get_current_session_key", return_value="_default"
        ), mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1", "BUTLER_DEV_AUTO_VERIFY": "0"}):
            _dev_engine_post_edit("patch", args, result)

        assert len(ds.edit_history) == 1
        rec = ds.edit_history[0]
        assert rec.operation == "patch"
        assert rec.patch_old == "foo"
        assert rec.patch_new == "bar"
        _active_states.clear()

    def test_post_edit_captures_write_content(self):
        from butler.core.tool_batch import _dev_engine_post_edit
        from butler.dev_engine.dev_loop import create_dev_state
        from butler.dev_engine.dev_state import DevPhase
        from butler.dev_engine.dev_tools import _active_states

        ds = create_dev_state("test")
        ds.phase = DevPhase.EDIT
        _active_states["_default"] = ds

        args = {"path": "/tmp/new.py", "content": "print('hello')"}
        result = json.dumps({"success": True, "path": "/tmp/new.py"})
        with mock.patch(
            "butler.execution_context.get_current_session_key", return_value="_default"
        ), mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1", "BUTLER_DEV_AUTO_VERIFY": "0"}):
            _dev_engine_post_edit("write_file", args, result)

        assert len(ds.edit_history) == 1
        rec = ds.edit_history[0]
        assert rec.operation == "write"
        assert rec.new_content == "print('hello')"
        _active_states.clear()

    def test_patch_tool_returns_path(self, tmp_path, monkeypatch):
        """Verify _tool_patch includes 'path' in result JSON."""
        from types import SimpleNamespace

        from butler.execution_context import use_execution_context

        workspace = tmp_path / "ws"
        workspace.mkdir()
        fpath = workspace / "_test_patch_path.py"
        fpath.write_text("hello world\n", encoding="utf-8")
        monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(workspace))

        orch = mock.MagicMock()  # noqa: magicmock-no-spec
        orch.project_manager.get_current.return_value = SimpleNamespace(workspace=workspace)

        try:
            with mock.patch(
                "butler.core.read_state.require_read_before_edit", return_value=None
            ), use_execution_context(orch, session_key="patch-test"):
                from butler.tools.file_io import _tool_patch

                result = json.loads(_tool_patch(str(fpath), "hello", "goodbye"))
                assert result.get("success") is True, f"Unexpected: {result}"
                assert "path" in result
        finally:
            fpath.unlink(missing_ok=True)


# ── G2: Auto-verify integration ────────────────────────────────


class TestAutoVerify:
    def test_post_edit_from_plan_primes_edit_phase(self):
        """Delegate child DevState starts in PLAN; first edit must still record."""
        from butler.core.tool_batch import _dev_engine_post_edit
        from butler.dev_engine.dev_loop import create_dev_state
        from butler.dev_engine.dev_state import DevPhase
        from butler.dev_engine.dev_tools import _active_states

        ds = create_dev_state("delegate task")
        assert ds.phase == DevPhase.PLAN
        _active_states["child::1"] = ds

        args = {"path": "/tmp/x.py", "old_string": "a", "new_string": "b"}
        result = json.dumps({"success": True, "path": "/tmp/x.py"})
        with mock.patch(
            "butler.execution_context.get_current_session_key", return_value="child::1"
        ), mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1", "BUTLER_DEV_AUTO_VERIFY": "0"}):
            _dev_engine_post_edit("patch", args, result)

        assert len(ds.edit_history) == 1
        assert ds.phase == DevPhase.VERIFY
        _active_states.clear()

    def test_post_edit_from_verify_allows_fix_loop(self):
        """After auto-verify failure (VERIFY), re-edit must record and re-verify."""
        from butler.core.tool_batch import _dev_engine_post_edit
        from butler.dev_engine.dev_loop import create_dev_state, transition
        from butler.dev_engine.dev_state import DevPhase
        from butler.dev_engine.dev_tools import _active_states

        ds = create_dev_state("fix loop")
        ds = transition(ds, "plan_trivial")
        ds = transition(ds, "edit_success")
        ds = transition(ds, "verify_fail")
        ds = transition(ds, "fix_applied")
        assert ds.phase == DevPhase.VERIFY
        _active_states["child::2"] = ds

        args = {"path": "/tmp/y.py", "old_string": "1", "new_string": "2"}
        result = json.dumps({"success": True, "path": "/tmp/y.py"})
        with mock.patch(
            "butler.execution_context.get_current_session_key", return_value="child::2"
        ), mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1", "BUTLER_DEV_AUTO_VERIFY": "0"}):
            _dev_engine_post_edit("patch", args, result)

        assert len(ds.edit_history) == 1
        assert ds.edit_history[0].path == "/tmp/y.py"
        assert ds.phase == DevPhase.VERIFY
        _active_states.clear()

    def test_post_edit_transitions_to_verify(self):
        """After successful edit, state advances from EDIT → VERIFY."""
        from butler.core.tool_batch import _dev_engine_post_edit
        from butler.dev_engine.dev_loop import create_dev_state
        from butler.dev_engine.dev_state import DevPhase
        from butler.dev_engine.dev_tools import _active_states

        ds = create_dev_state("test")
        ds.phase = DevPhase.EDIT
        _active_states["_default"] = ds

        args = {"path": "/tmp/x.py", "old_string": "a", "new_string": "b"}
        result = json.dumps({"success": True, "path": "/tmp/x.py"})
        with mock.patch(
            "butler.execution_context.get_current_session_key", return_value="_default"
        ), mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1", "BUTLER_DEV_AUTO_VERIFY": "0"}):
            _dev_engine_post_edit("patch", args, result)

        assert ds.phase == DevPhase.VERIFY
        _active_states.clear()


# ── G3: DevEnginePlugin ────────────────────────────────────────


class TestDevEnginePlugin:
    def test_before_model_injects_context(self):
        from butler.dev_engine.dev_loop import create_dev_state
        from butler.dev_engine.dev_tools import _active_states
        from butler.dev_engine.loop_plugin import DevEnginePlugin

        ds = create_dev_state("implement feature X")
        _active_states["test_sk"] = ds

        plugin = DevEnginePlugin(session_key="test_sk")
        msgs = [{"role": "system", "content": "You are a dev."}]
        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1"}):
            out = plugin.before_model(msgs)

        assert len(out) == 2
        injected = out[1]["content"]
        assert "<dev-engine-state>" in injected
        assert "PLAN" in injected
        _active_states.clear()

    def test_before_model_noop_without_state(self):
        from butler.dev_engine.dev_tools import _active_states
        from butler.dev_engine.loop_plugin import DevEnginePlugin

        _active_states.clear()
        plugin = DevEnginePlugin(session_key="nonexistent")
        msgs = [{"role": "user", "content": "hi"}]
        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1"}):
            out = plugin.before_model(msgs)

        assert len(out) == 1

    def test_after_tools_injects_diagnostics(self):
        from butler.dev_engine.dev_loop import create_dev_state
        from butler.dev_engine.dev_state import (
            Diagnostic,
            DiagSeverity,
            VerifyResult,
            VerifyStatus,
        )
        from butler.dev_engine.dev_tools import _active_states
        from butler.dev_engine.loop_plugin import DevEnginePlugin

        ds = create_dev_state("fix bug")
        ds.verify_result = VerifyResult(status=VerifyStatus.FAIL)
        ds.diagnostics = [
            Diagnostic(file="a.py", line=10, message="undefined name 'foo'", severity=DiagSeverity.ERROR)
        ]
        _active_states["test_sk2"] = ds

        plugin = DevEnginePlugin(session_key="test_sk2")
        msgs = [{"role": "user", "content": "fix it"}]
        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1", "BUTLER_DEV_DIAGNOSTICS_INJECT": "1"}):
            out = plugin.after_tools(msgs)

        assert len(out) == 2
        feedback = next(
            m["content"] for m in out
            if m.get("role") == "system" and "<dev-verify-feedback>" in m.get("content", "")
        )
        assert "undefined name" in feedback
        _active_states.clear()

    def test_after_tools_injects_when_diagnostics_empty(self):
        from butler.dev_engine.dev_loop import create_dev_state
        from butler.dev_engine.dev_state import VerifyResult, VerifyStatus
        from butler.dev_engine.dev_tools import _active_states
        from butler.dev_engine.loop_plugin import DevEnginePlugin

        ds = create_dev_state("fix bug")
        ds.verify_result = VerifyResult(
            status=VerifyStatus.FAIL,
            command="pytest -q",
            exit_code=1,
        )
        _active_states["test_sk3"] = ds

        plugin = DevEnginePlugin(session_key="test_sk3")
        msgs = [{"role": "user", "content": "fix it"}]
        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1", "BUTLER_DEV_DIAGNOSTICS_INJECT": "1"}):
            out = plugin.after_tools(msgs)

        assert len(out) == 2
        feedback = next(
            m["content"] for m in out
            if m.get("role") == "system" and "verify_failed" in m.get("content", "")
        )
        assert "pytest -q" in feedback
        _active_states.clear()

    def test_after_tools_injects_fix_hint_same_turn(self):
        from butler.dev_engine.dev_loop import create_dev_state
        from butler.dev_engine.dev_state import VerifyResult, VerifyStatus
        from butler.dev_engine.dev_tools import _active_states
        from butler.dev_engine.loop_plugin import DevEnginePlugin

        ds = create_dev_state("fix bug")
        ds.verify_result = VerifyResult(status=VerifyStatus.FAIL)
        ds._last_fix_hint = "structural"
        _active_states["test_sk4"] = ds

        plugin = DevEnginePlugin(session_key="test_sk4")
        with mock.patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1", "BUTLER_DEV_DIAGNOSTICS_INJECT": "1"}):
            out = plugin.after_tools([{"role": "user", "content": "x"}])

        feedback = next(
            m["content"] for m in out
            if m.get("role") == "system" and "fix_recommendation" in m.get("content", "")
        )
        assert "fix_recommendation: structural" in feedback
        assert ds._last_fix_hint is None
        _active_states.clear()


# ── G4: State transitions ──────────────────────────────────────


class TestStateTransitions:
    def test_search_symbols_triggers_transition(self):
        """dev_search_symbols with hits transitions LOCATE → EDIT."""
        import tempfile

        from butler.dev_engine.dev_loop import create_dev_state
        from butler.dev_engine.dev_state import DevPhase
        from butler.dev_engine.dev_tools import _active_states, tool_dev_search_symbols

        ds = create_dev_state("test")
        ds.phase = DevPhase.LOCATE
        _active_states["_default"] = ds

        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "example.py")
            with open(p, "w") as f:
                f.write("def my_unique_func_xyz():\n    pass\n")

            tool_dev_search_symbols("my_unique_func_xyz", td, session_key="_default")

        if ds.search_context:
            assert ds.phase == DevPhase.EDIT
        _active_states.clear()


# ── G5: fix_strategy integration ───────────────────────────────


class TestFixStrategyIntegration:
    def test_suggest_fix_action_returns_level(self):
        from butler.dev_engine.dev_loop import create_dev_state
        from butler.dev_engine.dev_state import Diagnostic, DiagSeverity
        from butler.dev_engine.fix_strategy import FixLevel, suggest_fix_action

        ds = create_dev_state("test")
        diags = [
            Diagnostic(file="a.py", line=1, message="unused import os", source="ruff", rule="F401")
        ]
        level = suggest_fix_action(diags, ds)
        assert level == FixLevel.DIRECT

    def test_suggest_rollback_on_stagnation(self):
        from butler.dev_engine.dev_loop import create_dev_state
        from butler.dev_engine.dev_state import (
            Diagnostic,
            DiagSeverity,
            VerifyResult,
            VerifyStatus,
        )
        from butler.dev_engine.fix_strategy import FixLevel, suggest_fix_action

        ds = create_dev_state("test", max_fix_rounds=4)
        ds.fix_count = 3
        ds.verify_result = VerifyResult(
            status=VerifyStatus.FAIL,
            diagnostics=[
                Diagnostic(file="x.py", line=1, message="error", severity=DiagSeverity.ERROR)
            ],
        )
        new_diags = [
            Diagnostic(file="x.py", line=1, message="error", severity=DiagSeverity.ERROR)
        ]
        level = suggest_fix_action(new_diags, ds)
        assert level == FixLevel.ROLLBACK


# ── Pre-edit snapshot capture ──────────────────────────────────


class TestPreEditSnapshot:
    def test_capture_and_fetch_snapshot(self):
        import tempfile

        from butler.core.tool_batch import (
            _capture_pre_edit_snapshot,
            _fetch_pre_edit_snapshot,
        )
        from butler.core.tool_batch_state import clear_pre_edit_snapshots

        clear_pre_edit_snapshots()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("original content\n")
            f.flush()
            fpath = f.name

        try:
            _capture_pre_edit_snapshot("write_file", {"path": fpath})
            snapshot = _fetch_pre_edit_snapshot(fpath)
            assert snapshot == "original content\n"
            assert _fetch_pre_edit_snapshot(fpath) is None
        finally:
            os.unlink(fpath)

    def test_capture_skips_non_edit_tools(self):
        from butler.core.tool_batch import _capture_pre_edit_snapshot
        from butler.core.tool_batch_state import clear_pre_edit_snapshots, pre_edit_snapshot_count

        clear_pre_edit_snapshots()
        _capture_pre_edit_snapshot("read_file", {"path": "/tmp/x.py"})
        assert pre_edit_snapshot_count() == 0
