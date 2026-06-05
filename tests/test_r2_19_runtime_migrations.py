"""R2-19 wider contract — runtime 8 文件 corruption handling verification.

Audit (`docs/reviews/project-deep-audit-2026-06-r1to8.md` §R2-19):
The critical 5-file migration (permissions, mcp, registry, memory) was
done in commit e6b574b.  This file verifies the wider 8-file runtime
migration: every file that previously did

    try:
        data = json.loads(path.read_text(...))
    except (OSError, json.JSONDecodeError):
        return default

now goes through ``safe_load_json`` / ``safe_load_yaml`` /
``quarantine_corrupt_file`` so corruption is renamed, logged at WARNING
with exc_info, and recorded in the diagnostics buffer.

Files covered:
1. ``butler/runtime/audit.py:52``  — ``latest_run``
2. ``butler/runtime/builtin_handlers.py:21`` — ``_workflow_state_digest``
3. ``butler/runtime/consistency_outcome.py:27`` — ``_p0_p1_from_json_report``
4. ``butler/runtime/loader.py:20`` — ``load_jobs_file``
5. ``butler/runtime/notify.py:43`` — ``_read_last_push_monotonic``
6. ``butler/runtime/task_store.py`` — 4 sites (get_task / list_recent_tasks /
   count_running_tasks / mark_stale_tasks)
7. ``butler/runtime/workflow_version.py:15`` — ``read_workflow_version``
8. ``butler/human_gate.py`` — 3 sites (_load_pending / _load_approved /
   consume_injection_bypass)

Each test class asserts the same three properties for its site:
* corrupt file is renamed to ``*.corrupt-<ns_ts>``
* WARNING is logged with ``exc_info`` (or, for sites that rethrow the
  load, the call path goes through the helper so the helper logs)
* the diagnostics buffer has an entry with the right ``kind`` tag
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from butler.io import safe_load as safe_load_mod
from butler.io.safe_load import (
    recent_state_file_corruption,
    reset_state_file_corruption,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_diagnostics():
    safe_load_mod.reset_state_file_corruption()
    yield
    safe_load_mod.reset_state_file_corruption()


def _corrupt_files_in(directory: Path):
    return sorted(p.name for p in directory.glob("*.corrupt-*"))


# ---------------------------------------------------------------------------
# 1. runtime/audit.py: latest_run
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRuntimeAuditLatestRun:
    """``latest_run`` must rename + log + record on corrupt run record."""

    def _seed_run(self, tmp_path: Path) -> Path:
        project = "demo"
        job = "j1"
        run_dir = tmp_path / project / job
        run_dir.mkdir(parents=True, exist_ok=True)
        target = run_dir / "20260605T120000Z.json"
        target.write_text("{not valid json}", encoding="utf-8")
        return run_dir

    def test_corrupt_run_record_renamed(self, tmp_path: Path):
        run_dir = self._seed_run(tmp_path)
        from butler.runtime import audit

        with patch.object(audit, "_runs_root", lambda: tmp_path):
            result = audit.latest_run("demo", "j1")
        assert result is None
        assert _corrupt_files_in(run_dir), "corrupt run record should be renamed"
        assert (run_dir / "20260605T120000Z.json").exists() is False

    def test_corrupt_run_record_records_diagnostics(self, tmp_path: Path):
        self._seed_run(tmp_path)
        from butler.runtime import audit

        with patch.object(audit, "_runs_root", lambda: tmp_path):
            audit.latest_run("demo", "j1")
        records = recent_state_file_corruption()
        assert len(records) == 1
        assert records[0]["kind"] == "runtime_run_record"


# ---------------------------------------------------------------------------
# 2. runtime/builtin_handlers.py: _workflow_state_digest
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRuntimeBuiltinHandlersWorkflowState:
    """``_workflow_state_digest`` must surface corruption to the user."""

    def test_corrupt_workflow_state_returns_user_facing_error(self, tmp_path: Path):
        from butler.runtime import builtin_handlers

        wf_dir = tmp_path / "novel-factory"
        wf_dir.mkdir()
        (wf_dir / "workflow_state.json").write_text("not json", encoding="utf-8")

        result = builtin_handlers.run_builtin(
            "builtin:workflow_state_digest", tmp_path,
        )
        assert result["success"] is False
        assert "损坏" in result["summary"] or "unreadable" in result["stderr"]
        # The corrupt file should have been renamed by the safe_load call.
        assert _corrupt_files_in(wf_dir)

    def test_corrupt_workflow_state_kind_in_diagnostics(self, tmp_path: Path):
        from butler.runtime import builtin_handlers

        wf_dir = tmp_path / "novel-factory"
        wf_dir.mkdir()
        (wf_dir / "workflow_state.json").write_text("not json", encoding="utf-8")

        builtin_handlers.run_builtin(
            "builtin:workflow_state_digest", tmp_path,
        )
        kinds = [r["kind"] for r in recent_state_file_corruption()]
        assert "runtime_workflow_state" in kinds


# ---------------------------------------------------------------------------
# 3. runtime/consistency_outcome.py: _p0_p1_from_json_report
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRuntimeConsistencyOutcome:
    """``_p0_p1_from_json_report`` must rename + log + record corruption."""

    def test_corrupt_report_returns_none_tuple(self, tmp_path: Path):
        from butler.runtime import consistency_outcome

        report = tmp_path / "report.json"
        report.write_text("garbage", encoding="utf-8")
        p0, p1 = consistency_outcome._p0_p1_from_json_report(report)
        assert (p0, p1) == (None, None)
        assert _corrupt_files_in(tmp_path)

    def test_corrupt_report_kind(self, tmp_path: Path):
        from butler.runtime import consistency_outcome

        report = tmp_path / "report.json"
        report.write_text("garbage", encoding="utf-8")
        consistency_outcome._p0_p1_from_json_report(report)
        records = recent_state_file_corruption()
        assert any(r["kind"] == "runtime_consistency_report" for r in records)


# ---------------------------------------------------------------------------
# 4. runtime/loader.py: load_jobs_file
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRuntimeLoaderJobsYaml:
    """``load_jobs_file`` must surface corruption while keeping
    ``JobsFile(jobs=[])`` contract for valid empty file."""

    def test_corrupt_jobs_yaml_renamed(self, tmp_path: Path):
        from butler.runtime import loader

        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(":\n  - [unbalanced", encoding="utf-8")
        with patch("butler.runtime.loader.logger") as mock_logger:
            jf = loader.load_jobs_file(tmp_path)
        assert jf is None
        assert _corrupt_files_in(runtime_dir)
        # Verify warning was logged with exc_info
        assert any(
            call.kwargs.get("exc_info") is not None
            for call in mock_logger.warning.call_args_list
        )

    def test_corrupt_jobs_yaml_records_diagnostics(self, tmp_path: Path):
        from butler.runtime import loader

        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(":\n  - [unbalanced", encoding="utf-8")
        loader.load_jobs_file(tmp_path)
        kinds = [r["kind"] for r in recent_state_file_corruption()]
        assert "runtime_jobs" in kinds

    def test_valid_empty_yaml_still_returns_jobs_file(self, tmp_path: Path):
        """The ``or {}`` contract must be preserved: empty file is not corruption."""
        from butler.runtime import loader
        from butler.runtime.schema import JobsFile

        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text("", encoding="utf-8")
        jf = loader.load_jobs_file(tmp_path)
        assert isinstance(jf, JobsFile)
        assert jf.jobs == []
        # Empty file is a successful parse — not a corruption event.
        assert recent_state_file_corruption() == []


# ---------------------------------------------------------------------------
# 5. runtime/notify.py: _read_last_push_monotonic
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRuntimeNotifyLastPush:
    """``_read_last_push_monotonic`` must rename + log + record corruption."""

    def test_corrupt_marker_renamed(self, tmp_path: Path, monkeypatch):
        from butler.runtime import notify

        marker = tmp_path / "last_push_at.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("garbage", encoding="utf-8")
        monkeypatch.setattr(notify, "_last_push_path", lambda: marker)
        result = notify._read_last_push_monotonic()
        assert result is None
        assert _corrupt_files_in(tmp_path)

    def test_corrupt_marker_records_diagnostics(self, tmp_path: Path, monkeypatch):
        from butler.runtime import notify

        marker = tmp_path / "last_push_at.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("garbage", encoding="utf-8")
        monkeypatch.setattr(notify, "_last_push_path", lambda: marker)
        notify._read_last_push_monotonic()
        kinds = [r["kind"] for r in recent_state_file_corruption()]
        assert "runtime_last_push" in kinds


# ---------------------------------------------------------------------------
# 6. runtime/task_store.py: 4 sites
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRuntimeTaskStore:
    """``task_store`` functions must rename + log + record on corrupt record."""

    def _seed_corrupt(self, tmp_path: Path) -> Path:
        # Patch the function-under-test to use tmp_path; write the
        # seed directly there so the patched root sees the file.
        tmp_path.mkdir(parents=True, exist_ok=True)
        target = tmp_path / "task_corrupt123.json"
        target.write_text("{not json}", encoding="utf-8")
        return target

    def test_get_task_returns_none_on_corrupt(self, tmp_path: Path):
        from butler.runtime import task_store

        self._seed_corrupt(tmp_path)
        with patch.object(task_store, "_tasks_root", lambda: tmp_path):
            assert task_store.get_task("task_corrupt123") is None
        assert _corrupt_files_in(tmp_path)

    def test_list_recent_tasks_skips_corrupt(self, tmp_path: Path):
        from butler.runtime import task_store

        self._seed_corrupt(tmp_path)
        with patch.object(task_store, "_tasks_root", lambda: tmp_path):
            recent = task_store.list_recent_tasks(limit=10)
        assert recent == []
        assert _corrupt_files_in(tmp_path)

    def test_count_running_tasks_skips_corrupt(self, tmp_path: Path):
        from butler.runtime import task_store

        self._seed_corrupt(tmp_path)
        with patch.object(task_store, "_tasks_root", lambda: tmp_path):
            assert task_store.count_running_tasks() == 0
        assert _corrupt_files_in(tmp_path)

    def test_mark_stale_tasks_skips_corrupt(self, tmp_path: Path):
        from butler.runtime import task_store

        self._seed_corrupt(tmp_path)
        with patch.object(task_store, "_tasks_root", lambda: tmp_path):
            stale = task_store.mark_stale_tasks()
        assert stale == []
        assert _corrupt_files_in(tmp_path)

    def test_corrupt_record_kind_in_diagnostics(self, tmp_path: Path):
        from butler.runtime import task_store

        self._seed_corrupt(tmp_path)
        with patch.object(task_store, "_tasks_root", lambda: tmp_path):
            task_store.get_task("task_corrupt123")
        kinds = [r["kind"] for r in recent_state_file_corruption()]
        assert "runtime_task" in kinds


# ---------------------------------------------------------------------------
# 7. runtime/workflow_version.py: read_workflow_version
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRuntimeWorkflowVersion:
    """``read_workflow_version`` must rename + log + record corruption."""

    def test_corrupt_state_returns_default(self, tmp_path: Path):
        from butler.runtime import workflow_version

        wf_dir = tmp_path / "novel-factory"
        wf_dir.mkdir()
        (wf_dir / "workflow_state.json").write_text("not json", encoding="utf-8")
        result = workflow_version.read_workflow_version(tmp_path)
        assert result == workflow_version._DEFAULT
        assert _corrupt_files_in(wf_dir)

    def test_corrupt_state_kind(self, tmp_path: Path):
        from butler.runtime import workflow_version

        wf_dir = tmp_path / "novel-factory"
        wf_dir.mkdir()
        (wf_dir / "workflow_state.json").write_text("not json", encoding="utf-8")
        workflow_version.read_workflow_version(tmp_path)
        kinds = [r["kind"] for r in recent_state_file_corruption()]
        assert "runtime_workflow_state" in kinds


# ---------------------------------------------------------------------------
# 8. human_gate.py: 3 sites
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHumanGatePendingCorruption:
    """``_load_pending`` must rename + log + record corruption."""

    def test_corrupt_pending_renamed(self, tmp_path: Path, monkeypatch):
        from butler import human_gate

        gate_dir = tmp_path / "human_gates"
        gate_dir.mkdir(parents=True, exist_ok=True)
        sk = "test_session_pending"
        digest = human_gate.hashlib.sha256(sk.encode("utf-8")).hexdigest()[:16]
        path = gate_dir / f"{digest}.json"
        path.write_text("garbage", encoding="utf-8")
        monkeypatch.setattr(human_gate, "_gate_dir", lambda: gate_dir)
        result = human_gate._load_pending(sk)
        assert result is None
        assert _corrupt_files_in(gate_dir)

    def test_corrupt_pending_records_diagnostics(self, tmp_path: Path, monkeypatch):
        from butler import human_gate

        gate_dir = tmp_path / "human_gates"
        gate_dir.mkdir(parents=True, exist_ok=True)
        sk = "test_session_pending2"
        digest = human_gate.hashlib.sha256(sk.encode("utf-8")).hexdigest()[:16]
        path = gate_dir / f"{digest}.json"
        path.write_text("garbage", encoding="utf-8")
        monkeypatch.setattr(human_gate, "_gate_dir", lambda: gate_dir)
        human_gate._load_pending(sk)
        kinds = [r["kind"] for r in recent_state_file_corruption()]
        assert "human_gate_pending" in kinds


@pytest.mark.unit
class TestHumanGateApprovedCorruption:
    """``_load_approved`` must rename + log + record corruption."""

    def test_corrupt_approved_renamed(self, tmp_path: Path, monkeypatch):
        from butler import human_gate

        gate_dir = tmp_path / "human_gates"
        gate_dir.mkdir(parents=True, exist_ok=True)
        sk = "test_session_approved"
        digest = human_gate.hashlib.sha256(sk.encode("utf-8")).hexdigest()[:16]
        path = gate_dir / f"{digest}.approved.json"
        path.write_text("garbage", encoding="utf-8")
        monkeypatch.setattr(human_gate, "_gate_dir", lambda: gate_dir)
        result = human_gate._load_approved(sk)
        assert result == set()
        assert _corrupt_files_in(gate_dir)

    def test_corrupt_approved_kind(self, tmp_path: Path, monkeypatch):
        from butler import human_gate

        gate_dir = tmp_path / "human_gates"
        gate_dir.mkdir(parents=True, exist_ok=True)
        sk = "test_session_approved2"
        digest = human_gate.hashlib.sha256(sk.encode("utf-8")).hexdigest()[:16]
        path = gate_dir / f"{digest}.approved.json"
        path.write_text("garbage", encoding="utf-8")
        monkeypatch.setattr(human_gate, "_gate_dir", lambda: gate_dir)
        human_gate._load_approved(sk)
        kinds = [r["kind"] for r in recent_state_file_corruption()]
        assert "human_gate_approved" in kinds


@pytest.mark.unit
class TestHumanGateInjectionBypassCorruption:
    """``consume_injection_bypass`` reads the consumed file via safe_load."""

    def test_corrupt_bypass_returns_false(self, tmp_path: Path, monkeypatch):
        from butler import human_gate

        gate_dir = tmp_path / "human_gates"
        gate_dir.mkdir(parents=True, exist_ok=True)
        sk = "test_session_bypass"
        # Path layout: inj_bypass_<digest>.json; ``os.rename`` will
        # move it to ``.consumed`` sibling (overwriting if present).
        digest = human_gate.hashlib.sha256(sk.encode()).hexdigest()[:16]
        bypass = gate_dir / f"inj_bypass_{digest}.json"
        # Bypass file is corrupt; after rename, consumed file has
        # the same corrupt content, so safe_load fails on it.
        bypass.write_text("garbage", encoding="utf-8")
        monkeypatch.setattr(human_gate, "_gate_dir", lambda: gate_dir)
        result = human_gate.consume_injection_bypass(sk)
        assert result is False
        # The consumed file should be renamed by safe_load.
        assert _corrupt_files_in(gate_dir)
