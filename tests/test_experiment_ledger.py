"""Experiment ledger, metrics parse, and research mode guards (PR6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.experiments.ledger import (
    append_record,
    best_record,
    experiments_ledger_path,
    list_recent,
    maybe_record_from_job_result,
)
from butler.experiments.metrics import parse_metrics_from_text, primary_metric
from butler.experiments.mode import (
    check_experiment_mode_block,
    experiment_mode_enabled,
    is_harness_path,
)


def test_parse_metric_lines():
    text = "noise\nMETRIC score=0.42\nMETRIC loss=0.1\n"
    rows = parse_metrics_from_text(text)
    assert len(rows) == 2
    assert rows[0]["metric_name"] == "score"
    assert rows[0]["metric_value"] == pytest.approx(0.42)


def test_metric_value_alias():
    assert primary_metric("metric_value=3.14\n")["metric_value"] == pytest.approx(3.14)


def test_append_and_best(tmp_path: Path):
    append_record(tmp_path, metric_name="score", metric_value=1.0, status="keep", hypothesis="a")
    append_record(tmp_path, metric_name="score", metric_value=2.0, status="keep", hypothesis="b")
    append_record(tmp_path, metric_name="score", metric_value=0.5, status="discard")
    best = best_record(tmp_path, metric_name="score")
    assert best is not None
    assert float(best["metric_value"]) == pytest.approx(2.0)
    assert len(list_recent(tmp_path, limit=2)) == 2
    assert experiments_ledger_path(tmp_path).is_file()


def test_record_from_job_stdout(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BUTLER_EXPERIMENT_LEDGER", "1")
    out = maybe_record_from_job_result(
        tmp_path,
        "harness-eval",
        {"success": True, "stdout": "METRIC score=0.9\n", "stderr": ""},
    )
    assert out is not None
    assert out["metric_name"] == "score"
    rows = list_recent(tmp_path, limit=1)
    assert rows[0]["status"] == "keep"


def test_experiment_mode_blocks_harness_write(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BUTLER_EXPERIMENT_MODE", "1")
    assert experiment_mode_enabled()
    harness = tmp_path / ".butler" / "harness" / "eval.sh"
    harness.parent.mkdir(parents=True)
    harness.write_text("#!/bin/sh\n", encoding="utf-8")
    assert is_harness_path(tmp_path, str(harness))
    err = check_experiment_mode_block(
        "patch",
        {"path": str(harness)},
        workspace=tmp_path,
    )
    assert err and "harness" in err


def test_experiment_mode_allows_experiments_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BUTLER_EXPERIMENT_MODE", "1")
    target = tmp_path / "experiments" / "main.py"
    target.parent.mkdir(parents=True)
    assert check_experiment_mode_block("write_file", {"path": str(target)}, workspace=tmp_path) is None
    err = check_experiment_mode_block(
        "write_file",
        {"path": str(tmp_path / "src" / "x.py")},
        workspace=tmp_path,
    )
    assert err and "experiments" in err
