"""L1 unit tests for butler.tool_guardrails."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from butler.tool_guardrails import (
    GuardrailConfig,
    GuardrailDecision,
    ToolCallGuardrailController,
    append_guidance,
    classify_tool_failure,
    synthetic_result,
)


def _strict_config(**kwargs) -> GuardrailConfig:
    return GuardrailConfig(
        exact_failure_warn_after=2,
        exact_failure_block_after=3,
        same_tool_failure_warn_after=3,
        same_tool_failure_halt_after=8,
        no_progress_warn_after=2,
        no_progress_block_after=3,
        **kwargs,
    )


@pytest.mark.unit
class TestBeforeCall:
    def test_first_call_allowed(self):
        ctrl = ToolCallGuardrailController()
        decision = ctrl.before_call("read_file", {"path": "a.py"})
        assert decision.allows_execution
        assert decision.action == "allow"

    def test_repeated_failure_warns(self):
        ctrl = ToolCallGuardrailController(config=_strict_config())
        args = {"path": "missing.py"}
        for _ in range(2):
            ctrl.after_call("read_file", args, '{"error": "not found"}', failed=True)
        decision = ctrl.after_call("read_file", args, '{"error": "not found"}', failed=True)
        assert decision.action == "warn"
        assert decision.code == "repeated_exact_failure_warning"

    def test_block_after_threshold(self):
        ctrl = ToolCallGuardrailController(config=_strict_config())
        args = {"command": "false"}
        for _ in range(3):
            ctrl.after_call("run_shell", args, '{"exit_code": 1}', failed=True)
        decision = ctrl.before_call("run_shell", args)
        assert decision.action == "block"
        assert not decision.allows_execution
        assert decision.code == "repeated_exact_failure_block"


@pytest.mark.unit
class TestIdempotentNoProgress:
    def test_idempotent_no_progress_warning(self):
        ctrl = ToolCallGuardrailController(config=_strict_config())
        args = {"path": "same.py"}
        result = '{"content": "unchanged"}'
        ctrl.after_call("read_file", args, result)
        decision = ctrl.after_call("read_file", args, result)
        assert decision.action == "warn"
        assert decision.code == "idempotent_no_progress_warning"

    def test_idempotent_no_progress_block(self):
        ctrl = ToolCallGuardrailController(config=_strict_config())
        args = {"path": "same.py"}
        result = '{"content": "same"}'
        for _ in range(3):
            ctrl.after_call("read_file", args, result)
        decision = ctrl.before_call("read_file", args)
        assert decision.action == "block"
        assert decision.code == "idempotent_no_progress_block"


@pytest.mark.unit
class TestThreadSafety:
    def test_concurrent_same_tool_failure_counts_are_exact(self):
        ctrl = ToolCallGuardrailController(
            config=GuardrailConfig(
                same_tool_failure_halt_after=50,
                same_tool_failure_warn_after=99,
                exact_failure_warn_after=99,
                exact_failure_block_after=99,
            )
        )
        barrier = threading.Barrier(25)

        def worker(idx: int) -> None:
            barrier.wait()
            ctrl.after_call(
                "search_files",
                {"query": str(idx)},
                '{"error": "x"}',
                failed=True,
            )

        with ThreadPoolExecutor(max_workers=25) as pool:
            list(pool.map(worker, range(50)))

        with ctrl._lock:
            assert ctrl._same_tool_failure_counts["search_files"] == 50
        assert ctrl.halt_decision is not None
        assert ctrl.halt_decision.action == "halt"

    def test_set_halt_decision_keeps_first_recorded_halt(self):
        ctrl = ToolCallGuardrailController()
        first = GuardrailDecision(action="block", code="first", message="first", tool_name="t")
        second = GuardrailDecision(action="halt", code="second", message="second", tool_name="t")
        ctrl.set_halt_decision(first)
        ctrl.set_halt_decision(second)
        assert ctrl.halt_decision == first


@pytest.mark.unit
class TestControllerLifecycle:
    def test_reset_for_turn_clears_state(self):
        ctrl = ToolCallGuardrailController(config=_strict_config())
        args = {"path": "a.py"}
        ctrl.after_call("read_file", args, '{"error": "x"}', failed=True)
        ctrl.after_call("read_file", args, '{"error": "x"}', failed=True)
        ctrl.reset_for_turn()
        decision = ctrl.before_call("read_file", args)
        assert decision.action == "allow"


@pytest.mark.unit
class TestSyntheticResult:
    def test_synthetic_result_returns_dict_json(self):
        decision = GuardrailDecision(
            action="block",
            code="repeated_exact_failure_block",
            message="Blocked duplicate call",
            count=3,
        )
        raw = synthetic_result(decision)
        data = json.loads(raw)
        assert data["error"] == "Blocked duplicate call"
        assert data["guardrail"]["action"] == "block"
        assert data["guardrail"]["count"] == 3

    def test_synthetic_result_supports_halt_action(self):
        decision = GuardrailDecision(
            action="halt",
            code="same_tool_failure_halt",
            message="Stopped read_file: failed 3 times this turn.",
            count=3,
        )
        raw = synthetic_result(decision)
        data = json.loads(raw)
        assert data["guardrail"]["action"] == "halt"
        assert data["guardrail"]["code"] == "same_tool_failure_halt"


@pytest.mark.unit
class TestClassifyToolFailure:
    def test_run_shell_nonzero_exit(self):
        failed, suffix = classify_tool_failure(
            "run_shell", json.dumps({"exit_code": 2})
        )
        assert failed
        assert "[exit 2]" in suffix

    def test_run_shell_success(self):
        failed, suffix = classify_tool_failure(
            "run_shell", json.dumps({"exit_code": 0, "stdout": "ok"})
        )
        assert not failed
        assert suffix == ""

    def test_dict_success_false(self):
        failed, suffix = classify_tool_failure(
            "read_file", json.dumps({"success": False})
        )
        assert failed
        assert suffix == " [error]"

    def test_plain_error_prefix(self):
        failed, suffix = classify_tool_failure("write_file", "Error: permission denied")
        assert failed
        assert suffix == " [error]"


@pytest.mark.unit
class TestAppendGuidance:
    def test_append_guidance_adds_warning_text(self):
        decision = GuardrailDecision(
            action="warn",
            code="same_tool_failure_warning",
            message="read_file failed 3 times this turn.",
            count=3,
        )
        out = append_guidance('{"ok": true}', decision)
        assert "Tool loop warning" in out
        assert "same_tool_failure_warning" in out
        assert "read_file failed" in out

    def test_append_guidance_unchanged_for_allow(self):
        decision = GuardrailDecision(action="allow")
        original = '{"ok": true}'
        assert append_guidance(original, decision) == original
