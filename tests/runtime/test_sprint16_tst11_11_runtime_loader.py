"""Sprint 16 TST-11-11: butler.runtime.loader 直测补全.

loader.py 之前 0 直测 (Audit TST-11-11 标记) — 覆盖:
  - load_jobs_file: 缺文件/坏 YAML/非 dict/defaults 注入/notify/approval 字段解析
  - find_job: 命中/未命中
  - list_jobs: enabled_only 过滤
"""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.runtime import loader
from butler.runtime.schema import ApprovalConfig, JobDef, JobsFile, NotifyConfig


# ── load_jobs_file ──


class TestLoadJobsFile:
    def test_returns_none_when_file_missing(self, tmp_path: Path):
        assert loader.load_jobs_file(tmp_path) is None

    def test_returns_none_on_invalid_yaml(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(":\n  - [unbalanced", encoding="utf-8")
        assert loader.load_jobs_file(tmp_path) is None

    def test_returns_none_when_top_level_not_dict(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text("- a\n- b\n", encoding="utf-8")
        assert loader.load_jobs_file(tmp_path) is None

    def test_returns_empty_jobs_on_empty_yaml(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text("", encoding="utf-8")
        jf = loader.load_jobs_file(tmp_path)
        assert isinstance(jf, JobsFile)
        assert jf.jobs == []

    def test_minimal_job(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(
            "version: 1\nproject: demo\njobs:\n  - id: j1\n",
            encoding="utf-8",
        )
        jf = loader.load_jobs_file(tmp_path)
        assert jf is not None
        assert jf.project == "demo"
        assert len(jf.jobs) == 1
        j = jf.jobs[0]
        assert j.id == "j1"
        assert j.mode == "readonly"  # default
        assert j.enabled is True  # default
        assert j.command == []  # default
        assert j.timeout_seconds == 900  # default

    def test_command_as_string_normalized_to_list(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(
            "jobs:\n  - id: j1\n    command: 'echo hi'\n",
            encoding="utf-8",
        )
        jf = loader.load_jobs_file(tmp_path)
        assert jf.jobs[0].command == ["echo hi"]

    def test_command_as_list_with_blanks_dropped(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(
            'jobs:\n  - id: j1\n    command:\n      - "echo a"\n      - ""\n      - "echo b"\n',
            encoding="utf-8",
        )
        jf = loader.load_jobs_file(tmp_path)
        assert jf.jobs[0].command == ["echo a", "echo b"]

    def test_defaults_override_per_job(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(
            "defaults:\n  timeout_seconds: 60\n  max_summary_chars: 200\n"
            "jobs:\n  - id: j1\n",
            encoding="utf-8",
        )
        jf = loader.load_jobs_file(tmp_path)
        j = jf.jobs[0]
        assert j.timeout_seconds == 60  # from defaults
        assert j.notify.max_summary_chars == 200  # from defaults

    def test_per_job_timeout_overrides_defaults(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(
            "defaults:\n  timeout_seconds: 60\njobs:\n  - id: j1\n    timeout_seconds: 30\n",
            encoding="utf-8",
        )
        jf = loader.load_jobs_file(tmp_path)
        assert jf.jobs[0].timeout_seconds == 30

    def test_notify_fields(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(
            "jobs:\n  - id: j1\n    notify:\n      on_success: false\n      on_failure: true\n      max_summary_chars: 500\n",
            encoding="utf-8",
        )
        jf = loader.load_jobs_file(tmp_path)
        n = jf.jobs[0].notify
        assert n.on_success is False
        assert n.on_failure is True
        assert n.max_summary_chars == 500

    def test_approval_fields(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(
            "jobs:\n  - id: j1\n    approval:\n      required: false\n      expires_hours: 12\n",
            encoding="utf-8",
        )
        jf = loader.load_jobs_file(tmp_path)
        a = jf.jobs[0].approval
        assert a.required is False
        assert a.expires_hours == 12

    def test_job_missing_id_is_skipped(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(
            "jobs:\n  - id: good\n  - description: 'no id'\n  - id: ''\n",
            encoding="utf-8",
        )
        jf = loader.load_jobs_file(tmp_path)
        assert [j.id for j in jf.jobs] == ["good"]

    def test_non_dict_job_items_skipped(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(
            "jobs:\n  - id: good\n  - 'string-not-dict'\n  - 42\n",
            encoding="utf-8",
        )
        jf = loader.load_jobs_file(tmp_path)
        assert [j.id for j in jf.jobs] == ["good"]


# ── find_job ──


class TestFindJob:
    def test_returns_match(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(
            "jobs:\n  - id: a\n  - id: b\n", encoding="utf-8",
        )
        j = loader.find_job(tmp_path, "b")
        assert j is not None
        assert j.id == "b"

    def test_returns_none_when_no_match(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(
            "jobs:\n  - id: a\n", encoding="utf-8",
        )
        assert loader.find_job(tmp_path, "missing") is None

    def test_returns_none_when_file_missing(self, tmp_path: Path):
        assert loader.find_job(tmp_path, "any") is None

    def test_strips_whitespace_on_lookup(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(
            "jobs:\n  - id: a\n", encoding="utf-8",
        )
        assert loader.find_job(tmp_path, "  a  ") is not None


# ── list_jobs ──


class TestListJobs:
    def test_returns_all_by_default(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(
            "jobs:\n  - id: a\n    enabled: true\n  - id: b\n    enabled: false\n  - id: c\n",
            encoding="utf-8",
        )
        jobs = loader.list_jobs(tmp_path)
        assert [j.id for j in jobs] == ["a", "b", "c"]

    def test_enabled_only_filters_disabled(self, tmp_path: Path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "jobs.yaml").write_text(
            "jobs:\n  - id: a\n    enabled: true\n  - id: b\n    enabled: false\n",
            encoding="utf-8",
        )
        jobs = loader.list_jobs(tmp_path, enabled_only=True)
        assert [j.id for j in jobs] == ["a"]

    def test_returns_empty_when_file_missing(self, tmp_path: Path):
        assert loader.list_jobs(tmp_path) == []
        assert loader.list_jobs(tmp_path, enabled_only=True) == []
