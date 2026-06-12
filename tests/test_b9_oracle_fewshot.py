"""Tests for B9 oracle few-shot injection."""

from __future__ import annotations

from butler.dev_engine.b9_live_fixed_tasks import B9_LIVE_FIXED_TASKS
from butler.dev_engine.b9_live_tuning import build_b9_delegate_args
from butler.dev_engine.b9_oracle_fewshot import (
    b9_oracle_fewshot_enabled,
    format_b9_oracle_fewshot_block,
)


def test_fewshot_block_contains_patterns():
    block = format_b9_oracle_fewshot_block(max_cases=2)
    assert "<b9-oracle-fewshot>" in block
    assert "logic bug" in block
    assert "import mismatch" in block


def test_fewshot_disabled(monkeypatch):
    monkeypatch.setenv("BUTLER_B9_ORACLE_FEWSHOT", "0")
    assert not b9_oracle_fewshot_enabled()
    assert format_b9_oracle_fewshot_block() == ""


def test_delegate_context_includes_fewshot(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_B9_ORACLE_FEWSHOT", "1")
    spec = next(t for t in B9_LIVE_FIXED_TASKS if t.task_id == "B9L_two_file_patch")
    args = build_b9_delegate_args(spec, tmp_path)
    assert "b9-oracle-fewshot" in args["context"]
