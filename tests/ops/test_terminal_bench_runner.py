"""Tests for the Terminal-Bench external anchor runner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from butler.eval_integration.oss import terminal_bench_runner as runner


def test_summarize_results_aggregates_tasks_and_tokens():
    metrics = runner.summarize_results(
        {
            "results": [
                {
                    "task_id": "fix-git",
                    "is_resolved": True,
                    "failure_mode": "unset",
                    "total_input_tokens": 100,
                    "total_output_tokens": 20,
                },
                {
                    "task_id": "fix-git",
                    "is_resolved": False,
                    "failure_mode": "FailureMode.TIMEOUT",
                    "total_input_tokens": 50,
                    "total_output_tokens": 5,
                },
                {
                    "task_id": "hello-world",
                    "is_resolved": False,
                    "failure_mode": "FailureMode.PARSE_ERROR",
                    "total_input_tokens": 10,
                    "total_output_tokens": 2,
                },
            ]
        },
        dataset="terminal-bench-core==0.1.1",
        agent="terminus-2",
        model="openai/test-model",
        run_dir="/tmp/run",
    )

    assert metrics["tasks"] == 2
    assert metrics["passed"] == 1
    assert metrics["pass_rate"] == 0.5
    assert metrics["attempts"] == 3
    assert metrics["input_tokens"] == 160
    assert metrics["output_tokens"] == 27
    assert metrics["failure_modes"] == {"unset": 1, "timeout": 1, "parse_error": 1}
    assert metrics["details"] == [
        {"taskId": "fix-git", "resolved": True, "attempts": 2},
        {"taskId": "hello-world", "resolved": False, "attempts": 1},
    ]


def test_summarize_results_accepts_trial_file_list():
    metrics = runner.summarize_results(
        [{"task_id": "hello-world", "is_resolved": True}],
        dataset="d",
        agent="oracle",
        model=None,
        run_dir="/tmp/run",
    )
    assert metrics["pass_rate"] == 1.0
    assert metrics["tasks"] == 1


def test_build_command_passes_subset_and_endpoint(monkeypatch):
    monkeypatch.setenv("BUTLER_EVAL_TB_TEMPERATURE", "0")
    monkeypatch.setenv("BUTLER_EVAL_TB_TEST_TIMEOUT", "600")
    monkeypatch.setenv("BUTLER_EVAL_TB_CLEANUP", "0")
    command = runner._build_command(
        binary="/usr/bin/tb",
        dataset="terminal-bench-core==0.1.1",
        tasks=["hello-world", "fix-git"],
        agent="terminus-2",
        model="openai/test-model",
        api_base="https://api.example.com/v1",
        output_dir=Path("/tmp/out"),
        run_id="run-1",
    )
    assert command.count("-t") == 2
    assert "openai/test-model" in command
    assert "api_base=https://api.example.com/v1" in command
    assert "temperature=0" in command
    assert "600" in command
    assert "--no-cleanup" in command


def test_run_returns_error_when_results_missing(tmp_path, monkeypatch):
    run_id = "missing-results"
    monkeypatch.setenv("BUTLER_EVAL_TB_BIN", "/usr/bin/tb")
    monkeypatch.setenv("BUTLER_EVAL_TB_OUT_DIR", str(tmp_path))
    monkeypatch.setenv("BUTLER_EVAL_TB_RUN_ID", run_id)
    monkeypatch.setenv("BUTLER_EVAL_TB_SUBSET", "hello-world")
    monkeypatch.setenv("BUTLER_EVAL_TB_AGENT", "oracle")
    monkeypatch.setattr(runner, "terminal_bench_available", lambda: True)
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout="no results", stderr=""
        ),
    )

    ok, metrics = runner.run_terminal_bench_eval()

    assert ok is False
    assert metrics["error"] == "Terminal-Bench 未产出 results.json"
    assert metrics["tasks"] == ["hello-world"]
    assert (tmp_path / run_id / "tb-eval.log").is_file()


def test_run_reads_results_file(tmp_path, monkeypatch):
    run_id = "with-results"
    monkeypatch.setenv("BUTLER_EVAL_TB_BIN", "/usr/bin/tb")
    monkeypatch.setenv("BUTLER_EVAL_TB_OUT_DIR", str(tmp_path))
    monkeypatch.setenv("BUTLER_EVAL_TB_RUN_ID", run_id)
    monkeypatch.setenv("BUTLER_EVAL_TB_SUBSET", "hello-world")
    monkeypatch.setenv("BUTLER_EVAL_TB_AGENT", "oracle")
    monkeypatch.setattr(runner, "terminal_bench_available", lambda: True)
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout="", stderr=""
        ),
    )
    run_root = tmp_path / run_id
    run_root.mkdir(parents=True)
    (run_root / "results.json").write_text(
        json.dumps(
            {
                "results": [
                    {"task_id": "hello-world", "is_resolved": True, "failure_mode": "unset"}
                ]
            }
        ),
        encoding="utf-8",
    )

    ok, metrics = runner.run_terminal_bench_eval()

    assert ok is True
    assert metrics["passed"] == 1
    assert metrics["pass_rate"] == 1.0


def test_run_reports_timeout(tmp_path, monkeypatch):
    run_id = "timeout"
    monkeypatch.setenv("BUTLER_EVAL_TB_BIN", "/usr/bin/tb")
    monkeypatch.setenv("BUTLER_EVAL_TB_OUT_DIR", str(tmp_path))
    monkeypatch.setenv("BUTLER_EVAL_TB_RUN_ID", run_id)
    monkeypatch.setenv("BUTLER_EVAL_TB_AGENT", "oracle")
    monkeypatch.setenv("BUTLER_EVAL_TB_TIMEOUT", "60")
    monkeypatch.setattr(runner, "terminal_bench_available", lambda: True)

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="tb", timeout=60, output=b"building")

    monkeypatch.setattr(runner.subprocess, "run", _timeout)

    ok, metrics = runner.run_terminal_bench_eval()

    assert ok is False
    assert "超时" in metrics["error"]
    assert metrics["elapsed_seconds"] >= 0


def test_run_skips_without_tb(monkeypatch):
    monkeypatch.setattr(runner, "tb_binary", lambda: None)
    ok, metrics = runner.run_terminal_bench_eval()
    assert ok is True
    assert metrics["skipped"] is True
