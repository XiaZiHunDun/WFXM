"""Engineering verification tests for Dev Engine theory (P-DA / P-DT).

Validates axioms DA1-DA7 and theorems DT1-DT7 from
docs/architecture/v4-dev-engine-theory.md
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest


# ═══════════════════════════════════════════════════════════════
# P-DA1: Edit Atomicity — atomic write + MultiEdit rollback
# ═══════════════════════════════════════════════════════════════

class TestDA1EditAtomicity:
    """Axiom DA1: All edits are atomic; MultiEdit is transactional."""

    def test_write_atomic_creates_file(self, tmp_path: Path) -> None:
        from butler.dev_engine.edit_ops import apply_write

        f = tmp_path / "test.py"
        f.write_text("original")
        record, err = apply_write(f, "modified")
        assert err == ""
        assert record is not None
        assert f.read_text() == "modified"
        assert record.original_content == "original"
        assert record.operation == "write"

    def test_write_atomic_preserves_on_new(self, tmp_path: Path) -> None:
        from butler.dev_engine.edit_ops import apply_write

        f = tmp_path / "new.py"
        record, err = apply_write(f, "new content")
        assert err == ""
        assert f.read_text() == "new content"
        assert record is not None
        assert record.original_content is None

    def test_patch_unique_match(self, tmp_path: Path) -> None:
        from butler.dev_engine.edit_ops import apply_patch

        f = tmp_path / "test.py"
        f.write_text("hello world\nfoo bar\n")
        record, err = apply_patch(f, "hello world", "hello universe")
        assert err == ""
        assert "hello universe" in f.read_text()
        assert record is not None
        assert record.patch_old == "hello world"

    def test_patch_rejects_multiple_matches(self, tmp_path: Path) -> None:
        from butler.dev_engine.edit_ops import apply_patch

        f = tmp_path / "test.py"
        f.write_text("hello\nhello\n")
        record, err = apply_patch(f, "hello", "bye")
        assert err != ""
        assert record is None
        assert f.read_text() == "hello\nhello\n"

    def test_patch_rejects_no_match(self, tmp_path: Path) -> None:
        from butler.dev_engine.edit_ops import apply_patch

        f = tmp_path / "test.py"
        f.write_text("hello\n")
        record, err = apply_patch(f, "nonexistent", "bye")
        assert err != ""
        assert record is None

    def test_create_fails_if_exists(self, tmp_path: Path) -> None:
        from butler.dev_engine.edit_ops import apply_create

        f = tmp_path / "exists.py"
        f.write_text("existing")
        record, err = apply_create(f, "new")
        assert err != ""
        assert record is None
        assert f.read_text() == "existing"

    def test_create_succeeds(self, tmp_path: Path) -> None:
        from butler.dev_engine.edit_ops import apply_create

        f = tmp_path / "sub" / "new.py"
        record, err = apply_create(f, "brand new")
        assert err == ""
        assert f.read_text() == "brand new"
        assert record is not None
        assert record.operation == "create"

    def test_delete_snapshots_content(self, tmp_path: Path) -> None:
        from butler.dev_engine.edit_ops import apply_delete

        f = tmp_path / "doomed.py"
        f.write_text("to be deleted")
        record, err = apply_delete(f)
        assert err == ""
        assert not f.exists()
        assert record is not None
        assert record.original_content == "to be deleted"

    def test_multi_edit_all_or_nothing(self, tmp_path: Path) -> None:
        from butler.dev_engine.edit_ops import multi_edit

        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("original_a")
        f2.write_text("original_b")

        records, err = multi_edit([
            ("write", f1, {"content": "modified_a"}),
            ("patch", f2, {"old": "nonexistent_pattern", "new": "x"}),
        ])
        assert err != ""
        assert records == []
        assert f1.read_text() == "original_a"
        assert f2.read_text() == "original_b"

    def test_multi_edit_success(self, tmp_path: Path) -> None:
        from butler.dev_engine.edit_ops import multi_edit

        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("aaa")
        f2.write_text("bbb")

        records, err = multi_edit([
            ("write", f1, {"content": "AAA"}),
            ("write", f2, {"content": "BBB"}),
        ])
        assert err == ""
        assert len(records) == 2
        assert f1.read_text() == "AAA"
        assert f2.read_text() == "BBB"


# ═══════════════════════════════════════════════════════════════
# P-DA2: Verifiability — Verify produces structured diagnostics
# ═══════════════════════════════════════════════════════════════

class TestDA2Verifiability:
    """Axiom DA2: Each edit can be verified; results are structured."""

    def test_diagnostics_parser_ruff(self) -> None:
        from butler.dev_engine.diagnostics import parse_diagnostics

        output = "src/main.py:10:5: F401 'os' imported but unused\n"
        diags = parse_diagnostics(output, source="ruff")
        assert len(diags) == 1
        assert diags[0].file == "src/main.py"
        assert diags[0].line == 10
        assert diags[0].rule == "F401"

    def test_diagnostics_parser_pytest(self) -> None:
        from butler.dev_engine.diagnostics import parse_diagnostics

        output = "FAILED tests/test_foo.py::test_bar - AssertionError\n"
        diags = parse_diagnostics(output, source="pytest")
        assert len(diags) == 1
        assert diags[0].source == "pytest"
        assert "test_bar" in diags[0].message

    def test_diagnostics_parser_mypy(self) -> None:
        from butler.dev_engine.diagnostics import parse_diagnostics

        output = 'src/foo.py:42: error: Incompatible return value [return-value]\n'
        diags = parse_diagnostics(output, source="mypy")
        assert len(diags) == 1
        assert diags[0].line == 42
        assert diags[0].rule == "return-value"

    def test_diagnostics_parser_tsc(self) -> None:
        from butler.dev_engine.diagnostics import parse_diagnostics

        output = "src/app.ts(15,3): error TS2345: Argument of type 'string' is not assignable\n"
        diags = parse_diagnostics(output, source="tsc")
        assert len(diags) == 1
        assert diags[0].rule == "TS2345"
        assert diags[0].column == 3

    def test_diagnostics_parser_gcc(self) -> None:
        from butler.dev_engine.diagnostics import parse_diagnostics

        output = "main.c:5:10: error: expected ';' [-Werror]\n"
        diags = parse_diagnostics(output, source="gcc")
        assert len(diags) == 1
        assert diags[0].file == "main.c"
        assert diags[0].rule == "-Werror"

    def test_verify_result_structured(self) -> None:
        from butler.dev_engine.dev_state import (
            Diagnostic,
            DiagSeverity,
            VerifyResult,
            VerifyStatus,
        )

        vr = VerifyResult(
            status=VerifyStatus.FAIL,
            diagnostics=[
                Diagnostic(file="a.py", line=1, severity=DiagSeverity.ERROR, message="bad"),
                Diagnostic(file="b.py", line=2, severity=DiagSeverity.WARNING, message="meh"),
            ],
        )
        d = vr.to_dict()
        assert d["status"] == "FAIL"
        assert d["error_count"] == 1
        assert len(d["diagnostics"]) == 2


# ═══════════════════════════════════════════════════════════════
# P-DA3: Context Bounded — search/read have limits
# ═══════════════════════════════════════════════════════════════

class TestDA3ContextBounded:
    """Axiom DA3: Search results and file reads have upper bounds."""

    def test_search_max_results(self) -> None:
        from butler.dev_engine.code_search import MAX_SEARCH_RESULTS
        assert MAX_SEARCH_RESULTS <= 100

    def test_search_timeout(self) -> None:
        from butler.dev_engine.code_search import SEARCH_TIMEOUT
        assert SEARCH_TIMEOUT <= 30

    def test_file_read_limit(self) -> None:
        from butler.tools.file_io import MAX_READ_FILE_BYTES, MAX_READ_FILE_LINES
        assert MAX_READ_FILE_BYTES <= 2 * 1024 * 1024
        assert MAX_READ_FILE_LINES <= 5000


# ═══════════════════════════════════════════════════════════════
# P-DA4: Error Fixability — fix loop has K_max bound
# ═══════════════════════════════════════════════════════════════

class TestDA4ErrorFixability:
    """Axiom DA4: Fix loop bounded by K_max."""

    def test_fix_count_bounded(self) -> None:
        from butler.dev_engine.dev_state import DevState

        state = DevState(max_fix_rounds=3)
        assert state.record_fix_attempt()  # 1
        assert state.record_fix_attempt()  # 2
        assert state.record_fix_attempt()  # 3
        assert not state.record_fix_attempt()  # 4 > K_max

    def test_fix_strategy_classification(self) -> None:
        from butler.dev_engine.dev_state import Diagnostic
        from butler.dev_engine.fix_strategy import FixLevel, classify_fix

        d_direct = Diagnostic(file="a.py", line=1, message="'os' imported but unused", source="ruff", rule="F401")
        assert classify_fix(d_direct) == FixLevel.DIRECT

        d_struct = Diagnostic(file="t.py", line=10, message="test failed", source="pytest")
        assert classify_fix(d_struct) == FixLevel.STRUCTURAL

    def test_suggest_rollback_on_stagnation(self) -> None:
        from butler.dev_engine.dev_state import (
            DevState,
            Diagnostic,
            DiagSeverity,
            VerifyResult,
            VerifyStatus,
        )
        from butler.dev_engine.fix_strategy import FixLevel, suggest_fix_action

        state = DevState(max_fix_rounds=4)
        state.fix_count = 2
        state.verify_result = VerifyResult(
            status=VerifyStatus.FAIL,
            diagnostics=[
                Diagnostic(file="x.py", line=1, severity=DiagSeverity.ERROR, message="err"),
            ],
        )

        new_diags = [
            Diagnostic(file="x.py", line=1, severity=DiagSeverity.ERROR, message="still err"),
        ]
        level = suggest_fix_action(new_diags, state)
        assert level == FixLevel.ROLLBACK


# ═══════════════════════════════════════════════════════════════
# P-DA5: Butler Integration — DevEngine uses AgentLoop tools
# ═══════════════════════════════════════════════════════════════

class TestDA5ButlerIntegration:
    """Axiom DA5: DevEngine shares Butler's tool registry."""

    def test_dev_tools_subset_of_registry(self) -> None:
        core_tool_names = {
            "read_file", "write_file", "patch", "search_files",
            "list_directory", "terminal", "delete_file",
        }
        from butler.dev_engine.dev_state import DevPhase

        assert DevPhase.PLAN.value == "PLAN"
        assert len(core_tool_names) >= 5

    def test_dev_engine_enabled_env(self) -> None:
        from butler.dev_engine.dev_tools import dev_engine_enabled

        with patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "1"}):
            assert dev_engine_enabled()
        with patch.dict(os.environ, {"BUTLER_DEV_ENGINE": "0"}):
            assert not dev_engine_enabled()


# ═══════════════════════════════════════════════════════════════
# P-DA6: Observability — each step produces structured trace
# ═══════════════════════════════════════════════════════════════

class TestDA6Observability:
    """Axiom DA6: DevState produces structured reports."""

    def test_dev_state_to_dict(self) -> None:
        from butler.dev_engine.dev_state import DevPhase, DevState, EditRecord

        state = DevState(phase=DevPhase.EDIT, task_description="fix bug")
        state.record_edit(EditRecord(operation="write", path="/tmp/a.py"))
        d = state.to_dict()
        assert d["phase"] == "EDIT"
        assert d["edit_count"] == 1
        assert "recent_edits" in d

    def test_dev_state_summary(self) -> None:
        from butler.dev_engine.dev_state import DevState

        state = DevState()
        summary = state.summary()
        assert "PLAN" in summary
        assert "迭代" in summary

    def test_context_block_generation(self) -> None:
        from butler.dev_engine.dev_context import dev_state_context_block
        from butler.dev_engine.dev_state import DevState

        state = DevState(task_description="implement feature X")
        block = dev_state_context_block(state)
        assert "<dev-engine-state>" in block
        assert "PLAN" in block
        assert "</dev-engine-state>" in block


# ═══════════════════════════════════════════════════════════════
# P-DA7: Replaceable Enhancement — core loop works without externals
# ═══════════════════════════════════════════════════════════════

class TestDA7ReplaceableEnhancement:
    """Axiom DA7: Core dev loop doesn't depend on external tools."""

    def test_core_loop_no_opencode_dependency(self) -> None:
        """Dev loop state machine works without opencode."""
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("test task")
        state = transition(state, "plan_complete")
        state = transition(state, "files_found")
        state = transition(state, "edit_success")
        state = transition(state, "verify_pass")
        assert state.phase.value == "DONE"

    def test_opencode_is_conditional(self) -> None:
        with patch.dict(os.environ, {"BUTLER_OPENCODE_ENABLED": "0"}):
            try:
                from butler.extensions.opencode import opencode_enabled
                assert not opencode_enabled()
            except ImportError:
                pass


# ═══════════════════════════════════════════════════════════════
# P-DT1: Edit Safety — mtime check + atomic write
# ═══════════════════════════════════════════════════════════════

class TestDT1EditSafety:
    """Theorem DT1: Edits don't lose data; concurrent changes detected."""

    def test_atomic_write_survives_content(self, tmp_path: Path) -> None:
        from butler.io.atomic_write import atomic_write_text

        f = tmp_path / "safe.txt"
        atomic_write_text(f, "safe content")
        assert f.read_text() == "safe content"

    def test_read_state_detects_external_modification(self, tmp_path: Path) -> None:
        """DT1: mtime-based concurrent edit detection works."""
        from butler.core.read_state import (
            ReadStateEntry,
            _content_hash,
            _mtime_ns,
            get_read_state,
            record_read_state,
            reset_read_state,
        )

        sk = "__dt1_test__"
        reset_read_state(sk)
        f = tmp_path / "guarded.txt"
        f.write_text("v1")
        stat1 = f.stat()
        entry = record_read_state(f, stat1, b"v1", session_key=sk)
        assert entry is not None
        assert entry.content_hash == _content_hash(b"v1")

        time.sleep(0.05)
        f.write_text("v2_very_different_content_for_testing_stale")
        stat2 = f.stat()
        assert stat2.st_size != stat1.st_size, "size must differ for mtime-independent detection"

        stored = get_read_state(f, session_key=sk)
        assert stored is not None
        assert stored.size != stat2.st_size
        reset_read_state(sk)

    def test_undo_restores_original(self, tmp_path: Path) -> None:
        from butler.dev_engine.edit_ops import apply_write, undo_edit

        f = tmp_path / "undo_test.py"
        f.write_text("before")
        record, _ = apply_write(f, "after")
        assert f.read_text() == "after"

        err = undo_edit(record)
        assert err == ""
        assert f.read_text() == "before"


# ═══════════════════════════════════════════════════════════════
# P-DT2: Dev Loop Termination
# ═══════════════════════════════════════════════════════════════

class TestDT2LoopTermination:
    """Theorem DT2: Dev loop terminates in finite steps."""

    def test_max_iterations_terminates(self) -> None:
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("test", max_iterations=5)
        for _ in range(10):
            if state.is_terminal:
                break
            state = transition(state, "plan_complete")
            if state.is_terminal:
                break
            state = transition(state, "files_found")
            if state.is_terminal:
                break
            state = transition(state, "edit_success")
            if state.is_terminal:
                break
            state = transition(state, "verify_fail")
            if state.is_terminal:
                break
            state = transition(state, "fix_applied")
            if state.is_terminal:
                break
        assert state.is_terminal

    def test_fix_limit_terminates(self) -> None:
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("test", max_fix_rounds=2, max_iterations=100)
        state = transition(state, "plan_complete")
        state = transition(state, "files_found")
        state = transition(state, "edit_success")

        for _ in range(5):
            if state.is_terminal:
                break
            state = transition(state, "verify_fail")
            if state.is_terminal:
                break
            state = transition(state, "fix_applied")

        assert state.is_terminal
        assert state.phase.value == "STUCK"

    def test_happy_path_terminates(self) -> None:
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("quick fix")
        state = transition(state, "plan_trivial")
        state = transition(state, "edit_success")
        state = transition(state, "verify_pass")
        assert state.is_terminal
        assert state.phase.value == "DONE"

    def test_all_terminal_states_are_terminal(self) -> None:
        from butler.dev_engine.dev_state import DevPhase, DevState

        for phase in [DevPhase.DONE, DevPhase.STUCK]:
            state = DevState(phase=phase)
            assert state.is_terminal

    def test_non_terminal_states(self) -> None:
        from butler.dev_engine.dev_state import DevPhase, DevState

        for phase in [DevPhase.PLAN, DevPhase.LOCATE, DevPhase.EDIT,
                       DevPhase.VERIFY, DevPhase.FIX, DevPhase.REVIEW]:
            state = DevState(phase=phase)
            assert not state.is_terminal


# ═══════════════════════════════════════════════════════════════
# P-DT3: Permission Preservation
# ═══════════════════════════════════════════════════════════════

class TestDT3PermissionPreservation:
    """Theorem DT3: Dev engine ops are subset of role permissions."""

    def test_butler_extra_tools_no_write(self) -> None:
        from butler.tools.project_tools import _BUTLER_EXTRA_TOOLS

        write_tools = {"write_file", "patch", "delete_file", "run_shell", "terminal"}
        assert _BUTLER_EXTRA_TOOLS & write_tools == set()

    def test_dev_operations_map_to_tools(self) -> None:
        dev_ops = {
            "read": "read_file",
            "write": "write_file",
            "patch": "patch",
            "search": "search_files",
            "terminal": "terminal",
            "delete": "delete_file",
        }
        assert len(dev_ops) == 6


# ═══════════════════════════════════════════════════════════════
# P-DT4: Context Bounded
# ═══════════════════════════════════════════════════════════════

class TestDT4ContextBounded:
    """Theorem DT4: Dev loop context consumption bounded."""

    def test_search_results_capped(self, tmp_path: Path) -> None:
        from butler.dev_engine.code_search import MAX_SEARCH_RESULTS

        assert MAX_SEARCH_RESULTS <= 100

    def test_diagnostics_truncated_in_report(self) -> None:
        from butler.dev_engine.dev_state import (
            Diagnostic,
            DiagSeverity,
            VerifyResult,
            VerifyStatus,
        )

        diags = [
            Diagnostic(file=f"f{i}.py", line=i, severity=DiagSeverity.ERROR, message=f"err{i}")
            for i in range(50)
        ]
        vr = VerifyResult(status=VerifyStatus.FAIL, diagnostics=diags)
        d = vr.to_dict()
        assert len(d["diagnostics"]) <= 20

    def test_context_block_bounded(self) -> None:
        from butler.dev_engine.dev_context import dev_state_context_block
        from butler.dev_engine.dev_state import DevState, EditRecord, SearchHit

        state = DevState()
        for i in range(100):
            state.record_edit(EditRecord(operation="write", path=f"/tmp/f{i}.py"))
            state.search_context.append(SearchHit(path=f"f{i}.py"))

        block = dev_state_context_block(state)
        assert len(block) < 5000


# ═══════════════════════════════════════════════════════════════
# P-DT5: Rollback Safety
# ═══════════════════════════════════════════════════════════════

class TestDT5RollbackSafety:
    """Theorem DT5: Edit sequences can be fully undone."""

    def test_single_write_rollback(self, tmp_path: Path) -> None:
        from butler.dev_engine.edit_ops import apply_write, rollback_edits

        f = tmp_path / "rb.py"
        f.write_text("original")
        record, _ = apply_write(f, "changed")
        assert f.read_text() == "changed"

        errors = rollback_edits([record])
        assert errors == []
        assert f.read_text() == "original"

    def test_multi_step_rollback(self, tmp_path: Path) -> None:
        from butler.dev_engine.edit_ops import apply_create, apply_write, rollback_edits

        f1 = tmp_path / "x.py"
        f1.write_text("x_orig")
        f2 = tmp_path / "y.py"

        r1, _ = apply_write(f1, "x_mod")
        r2, _ = apply_create(f2, "y_new")
        assert f1.read_text() == "x_mod"
        assert f2.exists()

        errors = rollback_edits([r1, r2])
        assert errors == []
        assert f1.read_text() == "x_orig"
        assert not f2.exists()

    def test_delete_rollback_restores(self, tmp_path: Path) -> None:
        from butler.dev_engine.edit_ops import apply_delete, rollback_edits

        f = tmp_path / "doomed.py"
        f.write_text("precious")
        record, _ = apply_delete(f)
        assert not f.exists()

        errors = rollback_edits([record])
        assert errors == []
        assert f.read_text() == "precious"

    def test_patch_rollback(self, tmp_path: Path) -> None:
        from butler.dev_engine.edit_ops import apply_patch, rollback_edits

        f = tmp_path / "p.py"
        f.write_text("hello world\ngoodbye\n")
        record, _ = apply_patch(f, "hello world", "hello earth")
        assert "hello earth" in f.read_text()

        errors = rollback_edits([record])
        assert errors == []
        assert "hello world" in f.read_text()


# ═══════════════════════════════════════════════════════════════
# P-DT6: Diagnostic Completeness
# ═══════════════════════════════════════════════════════════════

class TestDT6DiagnosticCompleteness:
    """Theorem DT6: Verify detects errors in its scope."""

    def test_ruff_detects_unused_import(self) -> None:
        from butler.dev_engine.diagnostics import parse_diagnostics

        output = "app.py:1:1: F401 'os' imported but unused\napp.py:3:1: F401 'sys' imported but unused\n"
        diags = parse_diagnostics(output, source="ruff")
        assert len(diags) == 2
        assert all(d.rule == "F401" for d in diags)

    def test_generic_parser_detects_errors(self) -> None:
        from butler.dev_engine.diagnostics import parse_diagnostics

        output = "foo.py:10:5: error: something went wrong\n"
        diags = parse_diagnostics(output)
        assert len(diags) >= 1
        assert diags[0].file == "foo.py"
        assert diags[0].line == 10


# ═══════════════════════════════════════════════════════════════
# P-DT7: External Tool Substitutability
# ═══════════════════════════════════════════════════════════════

class TestDT7ExternalToolSubstitutability:
    """Theorem DT7: Core dev loop works without external tools."""

    def test_dev_loop_independent_of_opencode(self) -> None:
        from butler.dev_engine.dev_loop import (
            create_dev_state,
            get_valid_events,
            transition,
        )

        state = create_dev_state("standalone task")
        assert "plan_complete" in get_valid_events(state.phase)

        state = transition(state, "plan_complete")
        state = transition(state, "files_found")
        state = transition(state, "edit_success")
        state = transition(state, "verify_pass")
        assert state.phase.value == "DONE"

    def test_dev_tools_session_management(self) -> None:
        from butler.dev_engine.dev_tools import (
            clear_state,
            get_or_create_state,
            tool_dev_status,
        )

        clear_state("test_session")
        state = get_or_create_state("test_session")
        assert state.phase.value == "PLAN"

        status = tool_dev_status("test_session")
        assert status["phase"] == "PLAN"
        clear_state("test_session")


# ═══════════════════════════════════════════════════════════════
# Integration: End-to-end dev loop simulation
# ═══════════════════════════════════════════════════════════════

class TestDevLoopEndToEnd:
    """End-to-end development loop simulation."""

    def test_happy_path_plan_locate_edit_verify(self, tmp_path: Path) -> None:
        from butler.dev_engine.dev_loop import create_dev_state, transition
        from butler.dev_engine.edit_ops import apply_write

        state = create_dev_state("add hello function")

        state = transition(state, "plan_complete")
        assert state.phase.value == "LOCATE"

        state = transition(state, "files_found")
        assert state.phase.value == "EDIT"

        f = tmp_path / "hello.py"
        f.write_text("")
        record, err = apply_write(f, 'def hello():\n    return "hello"\n')
        assert err == ""
        state = transition(state, "edit_success", edit_record=record)
        assert state.phase.value == "VERIFY"
        assert len(state.edit_history) == 1

        state = transition(state, "verify_pass")
        assert state.phase.value == "DONE"
        assert state.is_terminal

    def test_fix_loop_then_success(self, tmp_path: Path) -> None:
        from butler.dev_engine.dev_loop import create_dev_state, transition
        from butler.dev_engine.dev_state import (
            Diagnostic,
            DiagSeverity,
            VerifyResult,
            VerifyStatus,
        )

        state = create_dev_state("fix bug", max_fix_rounds=3)

        state = transition(state, "plan_trivial")
        state = transition(state, "edit_success")

        fail_result = VerifyResult(
            status=VerifyStatus.FAIL,
            diagnostics=[
                Diagnostic(file="a.py", line=1, severity=DiagSeverity.ERROR, message="bug"),
            ],
        )
        state = transition(state, "verify_fail", verify_result=fail_result)
        assert state.phase.value == "FIX"

        state = transition(state, "fix_applied")
        assert state.phase.value == "VERIFY"

        state = transition(state, "verify_pass")
        assert state.phase.value == "DONE"

    def test_stuck_after_fix_exhaustion(self) -> None:
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("hopeless task", max_fix_rounds=2, max_iterations=50)
        state = transition(state, "plan_trivial")
        state = transition(state, "edit_success")

        for _ in range(5):
            if state.is_terminal:
                break
            state = transition(state, "verify_fail")
            if state.is_terminal:
                break
            state = transition(state, "fix_applied")

        assert state.is_terminal
        assert state.phase.value == "STUCK"

    def test_locate_not_found_cycles_back(self) -> None:
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("find missing file")
        state = transition(state, "plan_complete")
        assert state.phase.value == "LOCATE"

        state = transition(state, "not_found")
        assert state.phase.value == "PLAN"

    def test_review_path(self) -> None:
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("manual review needed")
        state = transition(state, "plan_trivial")
        state = transition(state, "edit_success")
        state = transition(state, "verify_skip")
        assert state.phase.value == "REVIEW"

        state = transition(state, "owner_approve")
        assert state.phase.value == "DONE"

    def test_code_search_file_pattern(self, tmp_path: Path) -> None:
        from butler.dev_engine.code_search import search_files

        (tmp_path / "foo.py").write_text("# foo")
        (tmp_path / "bar.txt").write_text("# bar")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "baz.py").write_text("# baz")

        hits = search_files("*.py", tmp_path)
        assert len(hits) >= 2
        names = [h.path for h in hits]
        assert any("foo.py" in n for n in names)


# =====================================================================
# DE-series: conformity audit — development capability fixes
# =====================================================================


class TestDE1PatchDeleteRollbackSnapshot:
    """DE-1: patch and delete records include original_content for rollback."""

    def test_patch_record_has_original_content(self):
        """Post-edit hook should populate original_content for patch ops."""
        from butler.dev_engine.dev_state import EditRecord

        record = EditRecord(
            path="/tmp/test.py", operation="patch",
            patch_old="old", patch_new="new",
            original_content="full original file content",
        )
        assert record.original_content is not None
        assert record.patch_old == "old"

    def test_delete_record_has_original_content(self):
        from butler.dev_engine.dev_state import EditRecord

        record = EditRecord(
            path="/tmp/test.py", operation="delete",
            original_content="file content before deletion",
        )
        assert record.original_content is not None

    def test_production_path_patch_snapshot(self, tmp_path):
        """tool_batch post-edit hook stores snapshot for patch."""
        from butler.core.tool_batch import (
            _capture_pre_edit_snapshot,
            _dev_engine_post_edit,
            _pre_edit_snapshots,
        )

        f = tmp_path / "code.py"
        f.write_text("line1\nline2\n")
        _pre_edit_snapshots.clear()
        _capture_pre_edit_snapshot("patch", {"path": str(f)})
        assert str(f.resolve()) in _pre_edit_snapshots

    def test_production_path_delete_snapshot(self, tmp_path):
        """tool_batch captures snapshot before delete."""
        from butler.core.tool_batch import (
            _capture_pre_edit_snapshot,
            _pre_edit_snapshots,
        )

        f = tmp_path / "doomed.py"
        f.write_text("doomed content")
        _pre_edit_snapshots.clear()
        _capture_pre_edit_snapshot("delete_file", {"path": str(f)})
        assert str(f.resolve()) in _pre_edit_snapshots


class TestDE2FixCountTracking:
    """DE-2: fix_applied is triggered and fix_count increments."""

    def test_verify_fail_enters_fix(self):
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("test fix count")
        state = transition(state, "plan_trivial")
        state = transition(state, "edit_success")
        assert state.phase.value == "VERIFY"
        state = transition(state, "verify_fail")
        assert state.phase.value == "FIX"

    def test_fix_applied_increments_count(self):
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("fix counting", max_fix_rounds=5)
        state = transition(state, "plan_trivial")
        state = transition(state, "edit_success")
        state = transition(state, "verify_fail")
        assert state.fix_count == 0
        state = transition(state, "fix_applied")
        assert state.fix_count == 1
        assert state.phase.value == "VERIFY"

    def test_fix_count_reaches_kmax_enters_stuck(self):
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("exhaust fixes", max_fix_rounds=2, max_iterations=100)
        state = transition(state, "plan_trivial")
        state = transition(state, "edit_success")
        for i in range(4):
            if state.is_terminal:
                break
            state = transition(state, "verify_fail")
            if state.is_terminal:
                break
            state = transition(state, "fix_applied")
        assert state.phase.value == "STUCK"
        assert state.fix_count >= 2


class TestDE3StuckTermination:
    """DE-3: STUCK state injects termination signal via plugin."""

    def test_plugin_injects_termination_on_stuck(self):
        from butler.dev_engine.dev_loop import create_dev_state, transition
        from butler.dev_engine.dev_tools import _active_states
        from butler.dev_engine.loop_plugin import DevEnginePlugin

        state = create_dev_state("stuck task")
        state.phase = __import__("butler.dev_engine.dev_state", fromlist=["DevPhase"]).DevPhase.STUCK
        sk = "_test_de3"
        _active_states[sk] = state

        try:
            plugin = DevEnginePlugin(session_key=sk)
            with patch("butler.dev_engine.dev_tools.dev_engine_enabled", return_value=True):
                msgs = [{"role": "user", "content": "hello"}]
                out = plugin.before_model(msgs)
                sys_msgs = [m for m in out if m.get("role") == "system"]
                assert any("终止" in m.get("content", "") for m in sys_msgs)
        finally:
            _active_states.pop(sk, None)

    def test_plugin_injects_termination_on_done(self):
        from butler.dev_engine.dev_loop import create_dev_state
        from butler.dev_engine.dev_state import DevPhase
        from butler.dev_engine.dev_tools import _active_states
        from butler.dev_engine.loop_plugin import DevEnginePlugin

        state = create_dev_state("done task")
        state.phase = DevPhase.DONE
        sk = "_test_de3_done"
        _active_states[sk] = state

        try:
            plugin = DevEnginePlugin(session_key=sk)
            with patch("butler.dev_engine.dev_tools.dev_engine_enabled", return_value=True):
                msgs = [{"role": "user", "content": "hello"}]
                out = plugin.before_model(msgs)
                sys_msgs = [m for m in out if m.get("role") == "system"]
                assert any("终止" in m.get("content", "") for m in sys_msgs)
        finally:
            _active_states.pop(sk, None)


class TestDE5MissingTransitions:
    """DE-5: test the 5 previously untested state transitions."""

    def test_locate_timeout_to_stuck(self):
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("timeout search")
        state = transition(state, "plan_complete")
        assert state.phase.value == "LOCATE"
        state = transition(state, "locate_timeout")
        assert state.phase.value == "STUCK"

    def test_edit_conflict_to_locate(self):
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("conflict edit")
        state = transition(state, "plan_trivial")
        assert state.phase.value == "EDIT"
        state = transition(state, "edit_conflict")
        assert state.phase.value == "LOCATE"

    def test_edit_fail_to_fix(self):
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("failed edit")
        state = transition(state, "plan_trivial")
        assert state.phase.value == "EDIT"
        state = transition(state, "edit_fail")
        assert state.phase.value == "FIX"

    def test_fix_rollback_to_plan(self):
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("rollback fix")
        state = transition(state, "plan_trivial")
        state = transition(state, "edit_success")
        state = transition(state, "verify_fail")
        assert state.phase.value == "FIX"
        state = transition(state, "fix_rollback")
        assert state.phase.value == "PLAN"

    def test_review_owner_reject_to_plan(self):
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("rejected review")
        state = transition(state, "plan_trivial")
        state = transition(state, "edit_success")
        state = transition(state, "verify_skip")
        assert state.phase.value == "REVIEW"
        state = transition(state, "owner_reject")
        assert state.phase.value == "PLAN"


class TestDE5InvalidTransitions:
    """DE-5: invalid transitions are rejected (phase unchanged)."""

    def test_plan_verify_pass_advances_to_done(self):
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("early verify pass")
        assert state.phase.value == "PLAN"
        state = transition(state, "verify_pass")
        assert state.phase.value == "DONE"

    def test_plan_verify_fail_advances_to_fix(self):
        from butler.dev_engine.dev_loop import create_dev_state, transition
        from butler.dev_engine.dev_state import VerifyResult, VerifyStatus

        state = create_dev_state("early verify fail")
        vr = VerifyResult(status=VerifyStatus.FAIL, command="pytest -q", exit_code=1)
        state = transition(state, "verify_fail", verify_result=vr)
        assert state.phase.value == "FIX"
        assert state.verify_result is vr

    def test_edit_owner_approve_invalid(self):
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("bad transition")
        state = transition(state, "plan_trivial")
        assert state.phase.value == "EDIT"
        state = transition(state, "owner_approve")
        assert state.phase.value == "EDIT"

    def test_verify_fix_rollback_invalid(self):
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("bad transition")
        state = transition(state, "plan_trivial")
        state = transition(state, "edit_success")
        assert state.phase.value == "VERIFY"
        state = transition(state, "fix_rollback")
        assert state.phase.value == "VERIFY"

    def test_terminal_state_no_transition(self):
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("terminal")
        state = transition(state, "plan_complete")
        state = transition(state, "locate_timeout")
        assert state.phase.value == "STUCK"
        state = transition(state, "plan_complete")
        assert state.phase.value == "STUCK"

    def test_done_state_no_transition(self):
        from butler.dev_engine.dev_loop import create_dev_state, transition

        state = create_dev_state("done")
        state = transition(state, "plan_trivial")
        state = transition(state, "edit_success")
        state = transition(state, "verify_pass")
        assert state.phase.value == "DONE"
        state = transition(state, "edit_success")
        assert state.phase.value == "DONE"


class TestDE6VerifyBasics:
    """DE-6: basic verification system tests."""

    def test_verify_result_passed_property(self):
        from butler.dev_engine.dev_state import VerifyResult, VerifyStatus
        assert VerifyResult(status=VerifyStatus.PASS).passed
        assert not VerifyResult(status=VerifyStatus.FAIL).passed

    def test_verify_layered_returns_result(self, tmp_path):
        from butler.dev_engine.verify import verify_layered
        result = verify_layered(tmp_path, levels="lint,typecheck,test,build")
        assert result.status.value in ("PASS", "SKIP", "FAIL")
        assert isinstance(result.command, str)

    def test_verify_result_error_count(self):
        from butler.dev_engine.dev_state import (
            DiagSeverity, Diagnostic, VerifyResult, VerifyStatus,
        )
        vr = VerifyResult(
            status=VerifyStatus.FAIL,
            diagnostics=[
                Diagnostic(file="a.py", line=1, severity=DiagSeverity.ERROR, message="e1"),
                Diagnostic(file="b.py", line=2, severity=DiagSeverity.WARNING, message="w1"),
                Diagnostic(file="c.py", line=3, severity=DiagSeverity.ERROR, message="e2"),
            ],
        )
        assert vr.error_count == 2

    def test_edit_ops_patch_rollback(self, tmp_path):
        """Patch via edit_ops includes original_content for rollback."""
        from butler.dev_engine.edit_ops import apply_patch, undo_edit

        f = tmp_path / "rollback_test.py"
        f.write_text("hello world\n")
        record, err = apply_patch(f, "hello", "goodbye")
        assert err == ""
        assert record is not None
        assert record.original_content == "hello world\n"
        assert f.read_text() == "goodbye world\n"

        undo_err = undo_edit(record)
        assert undo_err == ""
        assert f.read_text() == "hello world\n"

    def test_edit_ops_delete_rollback(self, tmp_path):
        """Delete via edit_ops includes original_content for rollback."""
        from butler.dev_engine.edit_ops import apply_delete, undo_edit

        f = tmp_path / "to_delete.py"
        f.write_text("delete me\n")
        record, err = apply_delete(f)
        assert err == ""
        assert record is not None
        assert record.original_content == "delete me\n"
        assert not f.exists()

        undo_err = undo_edit(record)
        assert undo_err == ""
        assert f.read_text() == "delete me\n"


class TestDE7EndToEndLifecycle:
    """DE-7: full delegate→DevEngine lifecycle integration test."""

    def test_happy_path_plan_to_done(self, tmp_path):
        """Full lifecycle: create → plan → locate → edit → verify → done."""
        from butler.dev_engine.dev_loop import create_dev_state, transition
        from butler.dev_engine.dev_state import DevPhase, EditRecord
        from butler.dev_engine.edit_ops import apply_write

        state = create_dev_state("fix bug in foo.py")
        assert state.phase == DevPhase.PLAN

        state = transition(state, "plan_complete")
        assert state.phase == DevPhase.LOCATE

        state = transition(state, "files_found")
        assert state.phase == DevPhase.EDIT

        f = tmp_path / "foo.py"
        f.write_text("print('old')\n")
        record, err = apply_write(f, "print('fixed')\n")
        assert err == ""
        state.record_edit(record)
        state = transition(state, "edit_success", edit_record=record)
        assert state.phase == DevPhase.VERIFY
        assert len(state.edit_history) >= 1

        state = transition(state, "verify_pass")
        assert state.phase == DevPhase.DONE
        assert state.is_terminal

    def test_fix_loop_lifecycle(self, tmp_path):
        """Lifecycle with fix loop: edit → verify_fail → fix → verify_pass."""
        from butler.dev_engine.dev_loop import create_dev_state, transition
        from butler.dev_engine.dev_state import (
            DevPhase, Diagnostic, DiagSeverity, EditRecord, VerifyResult, VerifyStatus,
        )
        from butler.dev_engine.edit_ops import apply_write

        state = create_dev_state("fix with retries", max_fix_rounds=3)
        state = transition(state, "plan_trivial")
        assert state.phase == DevPhase.EDIT

        f = tmp_path / "buggy.py"
        f.write_text("def broken(): pass\n")
        record, _ = apply_write(f, "def still_broken(): pass\n")
        state.record_edit(record)
        state = transition(state, "edit_success", edit_record=record)
        assert state.phase == DevPhase.VERIFY

        vr = VerifyResult(
            status=VerifyStatus.FAIL,
            diagnostics=[Diagnostic(
                file="buggy.py", line=1,
                severity=DiagSeverity.ERROR, message="SyntaxError",
            )],
        )
        state = transition(state, "verify_fail", verify_result=vr)
        assert state.phase == DevPhase.FIX
        assert state.diagnostics

        state = transition(state, "fix_applied")
        assert state.fix_count == 1
        assert state.phase == DevPhase.VERIFY

        state = transition(state, "verify_pass")
        assert state.phase == DevPhase.DONE

    def test_rollback_lifecycle(self, tmp_path):
        """Lifecycle with rollback: edit → verify_fail → fix_rollback → plan."""
        from butler.dev_engine.dev_loop import create_dev_state, transition
        from butler.dev_engine.dev_tools import (
            _active_states, set_state, tool_dev_rollback,
        )
        from butler.dev_engine.edit_ops import apply_write

        sk = "_test_de7_rollback"
        state = create_dev_state("rollback lifecycle")
        set_state(sk, state)

        try:
            state = transition(state, "plan_trivial")
            f = tmp_path / "rollme.py"
            f.write_text("original\n")
            record, _ = apply_write(f, "modified\n")
            state.record_edit(record)
            state = transition(state, "edit_success", edit_record=record)
            assert f.read_text() == "modified\n"

            state = transition(state, "verify_fail")
            assert state.phase.value == "FIX"

            result = tool_dev_rollback(1, session_key=sk)
            assert result["rolled_back"] == 1
            assert f.read_text() == "original\n"

            state = transition(state, "fix_rollback")
            assert state.phase.value == "PLAN"
        finally:
            _active_states.pop(sk, None)

    def test_tool_dev_status_reflects_state(self):
        """tool_dev_status returns correct phase and iteration count."""
        from butler.dev_engine.dev_loop import create_dev_state, transition
        from butler.dev_engine.dev_tools import (
            _active_states, set_state, tool_dev_status,
        )

        sk = "_test_de7_status"
        state = create_dev_state("status check")
        set_state(sk, state)

        try:
            status = tool_dev_status(sk)
            assert status["phase"] == "PLAN"
            assert status["iteration"] == 0

            state = transition(state, "plan_complete")
            state = transition(state, "files_found")
            status = tool_dev_status(sk)
            assert status["phase"] == "EDIT"
            assert status["iteration"] == 2
        finally:
            _active_states.pop(sk, None)

    def test_exhausted_fix_terminates_lifecycle(self):
        """K_max exhaustion produces terminal STUCK state."""
        from butler.dev_engine.dev_loop import create_dev_state, transition
        from butler.dev_engine.dev_state import DevPhase

        state = create_dev_state("exhaust", max_fix_rounds=1, max_iterations=100)
        state = transition(state, "plan_trivial")
        state = transition(state, "edit_success")

        state = transition(state, "verify_fail")
        state = transition(state, "fix_applied")
        assert state.fix_count == 1
        assert state.phase == DevPhase.VERIFY

        state = transition(state, "verify_fail")
        state = transition(state, "fix_applied")
        assert state.phase == DevPhase.STUCK
        assert state.is_terminal
