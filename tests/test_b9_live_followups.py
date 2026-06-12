"""Tests for B9 LIVE follow-up fixes (workspace, patch args, rescue overrides)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest


class TestSafeRootShim:
    def test_get_tool_safe_root_importable(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))
        from butler.tools.safe_root import get_tool_safe_root

        assert get_tool_safe_root().resolve() == tmp_path.resolve()

    def test_dev_verify_handler_resolves_workspace(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))
        from butler.dev_engine.dev_tools import _handler_dev_verify

        raw = _handler_dev_verify(levels="lint")
        data = json.loads(raw)
        assert "error" not in data or "No module named" not in str(data.get("error", ""))


class TestToolArgNormalize:
    def test_patch_file_alias_maps_to_path(self):
        from butler.tools.tool_arg_normalize import normalize_tool_args

        out = normalize_tool_args("patch", {"file": "a.py", "old_string": "x", "new_string": "y"})
        assert out["path"] == "a.py"

    def test_validate_patch_missing_path(self):
        from butler.tools.tool_arg_normalize import validate_tool_args

        err = validate_tool_args("patch", {"old_string": "a", "new_string": "b"})
        assert err is not None
        assert err["code"] == "TOOL_ARGS_INVALID"
        assert "path" in err["missing"]
        assert "hint" in err

    def test_validate_patch_allows_empty_new_string(self):
        from butler.tools.tool_arg_normalize import validate_tool_args

        assert validate_tool_args("patch", {"path": "a.py", "old_string": "x", "new_string": ""}) is None

    def test_dev_search_symbols_query_alias_maps_to_name(self):
        from butler.tools.tool_arg_normalize import normalize_tool_args, validate_tool_args

        out = normalize_tool_args("dev_search_symbols", {"query": "my_func"})
        assert out["name"] == "my_func"
        assert validate_tool_args("dev_search_symbols", out) is None

    def test_dispatch_patch_missing_args_returns_structured_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))
        from butler.tools.registry import dispatch_tool

        raw = dispatch_tool("patch", {"old_string": "x"})
        data = json.loads(raw)
        assert data.get("code") == "TOOL_ARGS_INVALID"
        assert "path" in data.get("missing", [])
        assert "missing 1 required positional argument" not in data.get("error", "").lower()


class TestDelegateChildProjectResolution:
    def test_child_session_inherits_parent_chat_binding(self):
        from butler.project.manager import ProjectManager
        from butler.project.model import Project

        pm = ProjectManager.__new__(ProjectManager)
        pm._initialized = True
        pm._projects = {}
        pm._chat_project = {}
        pm._on_switch_callbacks = []
        pm.current_project = ""
        pm._default_project = ""
        pm._lock = __import__("threading").Lock()
        ws = Path("/tmp/b9-ws")
        pm._projects["__b9_live_benchmark__"] = Project(
            name="__b9_live_benchmark__",
            type="software",
            description="test",
            workspace=ws,
        )
        pm.switch_project_for_chat(platform="b9", chat_id="benchmark", name="__b9_live_benchmark__")

        child = "b9:benchmark::delegate:abc123"
        name = pm.resolve_active_project_name(session_key=child)
        assert name == "__b9_live_benchmark__"
        proj = pm.get_current(session_key=child)
        assert proj is not None
        assert Path(proj.workspace) == ws


class TestVerifyOutputTail:
    def test_after_tools_includes_output_tail(self):
        from butler.dev_engine.dev_loop import create_dev_state
        from butler.dev_engine.dev_state import VerifyResult, VerifyStatus
        from butler.dev_engine.dev_tools import _active_states
        from butler.dev_engine.loop_plugin import DevEnginePlugin

        ds = create_dev_state("x")
        ds.verify_result = VerifyResult(
            status=VerifyStatus.FAIL,
            command="pytest -q",
            exit_code=1,
            output_tail="FAILED test_b9.py::test_mul - assert 5 == 6",
        )
        _active_states["sk_tail"] = ds
        plugin = DevEnginePlugin(session_key="sk_tail")
        with mock.patch.dict("os.environ", {"BUTLER_DEV_ENGINE": "1", "BUTLER_DEV_DIAGNOSTICS_INJECT": "1"}):
            out = plugin.after_tools([{"role": "user", "content": "fix"}])
        assert "output_tail:" in out[-1]["content"]
        assert "assert 5 == 6" in out[-1]["content"]
        _active_states.clear()


class TestMineDelegateFailures:
    def test_mine_signatures_from_audit(self, tmp_path, monkeypatch):
        from butler.ops.b9_failure_analysis import mine_delegate_failure_signatures

        audit = tmp_path / "audit" / "delegate_failures.jsonl"
        audit.parent.mkdir(parents=True)
        audit.write_text(
            '{"task_preview":"[category:b9-benchmark] fix import","issues":["ModuleNotFoundError: No module named helper"],"failure_reason":"verify_failed"}\n'
            '{"task_preview":"[category:b9-benchmark] fix mul","issues":["assert 5 == 6"],"failure_reason":"verify_failed"}\n'
            '{"task_preview":"[category:b9-benchmark] fix mul","issues":["assert 5 == 6"],"failure_reason":"verify_failed"}\n',
            encoding="utf-8",
        )
        monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
        out = mine_delegate_failure_signatures(min_count=2)
        assert out["total"] == 3
        sigs = {s["signature"] for s in out["signatures"]}
        assert "assert:5" in sigs or "import:helper" in sigs


class TestB9FailureClassOverrides:
    def test_apply_when_wrong_patch_dominant(self, tmp_path, monkeypatch):
        from butler.ops.eval_config_overrides import apply_b9_failure_class_overrides, load_overrides

        monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)

        analysis = {
            "total": 14,
            "by_classification": {"wrong_patch": 9, "passed": 4, "no_edit": 1},
        }
        action = apply_b9_failure_class_overrides(analysis)
        assert action is not None
        data = load_overrides()
        assert data.get("b9_enhanced_delegate_context") is True
        assert data.get("coding_guidance_max_cases") == 8

    def test_enhanced_delegate_context_when_flag_set(self, tmp_path, monkeypatch):
        monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)
        from butler.ops.eval_config_overrides import save_overrides

        save_overrides({"b9_enhanced_delegate_context": True})
        from butler.dev_engine.b9_live_tuning import build_b9_delegate_context

        ctx = build_b9_delegate_context(tmp_path)
        assert "assert X == Y" in ctx
        assert "old_string" in ctx


class TestB9LiveRescueOverride:
    def test_maybe_apply_b9_live_rescue_writes_overrides(self, tmp_path, monkeypatch):
        from butler.config import get_butler_home
        from butler.ops.eval_actions import maybe_apply_b9_live_rescue
        from butler.ops.eval_config_overrides import load_overrides

        monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)
        (tmp_path / "audit").mkdir(parents=True, exist_ok=True)

        class _R:
            def __init__(self, task_id: str, passed: bool):
                self.task_id = task_id
                self.passed = passed

        class _Report:
            results = [
                _R("B9L_two_file_patch", False),
                _R("B9L_pytest_fix_impl", False),
                _R("B9L_stuck_unsolvable", True),
            ]

        action = maybe_apply_b9_live_rescue(_Report(), min_solvable_rate=0.5)
        assert action is not None
        assert action["trigger"] == "b9_live_low_pass"
        data = load_overrides()
        assert data.get("delegate_max_iterations", 0) >= 24
