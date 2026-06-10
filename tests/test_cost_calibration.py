"""D4 cost calibration — rollup, baseline, /成本 integration."""

from __future__ import annotations

import json
from datetime import date

import pytest

from butler.ops.cost_calibration import (
    CostRollup,
    compare_to_baseline,
    events_path_for,
    format_cost_with_calibration,
    format_rollup_lines,
    load_baseline,
    rollup_period,
    save_baseline,
)
from butler.ops.cost_tracker import SessionCost, get_session_cost, reset_session_cost


@pytest.fixture(autouse=True)
def _isolate_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_COST_CALIBRATION_PERSIST", "1")
    yield


def _write_events(day: date, rows: list[dict]) -> None:
    path = events_path_for(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_rollup_aggregates_llm_and_tools():
    today = date.today()
    _write_events(
        today,
        [
            {"kind": "llm", "input_tokens": 1000, "output_tokens": 200, "model": "minimax-m2.7", "estimated_usd": 0.01},
            {"kind": "tool", "tool": "memo_search", "bucket": "pim"},
            {"kind": "tool", "tool": "delegate_task", "bucket": "dev"},
            {"kind": "tool", "tool": "run_workflow", "bucket": "pm"},
        ],
    )
    rollup = rollup_period(days=1)
    assert rollup.llm_calls == 1
    assert rollup.input_tokens == 1000
    assert rollup.tool_calls_pim == 1
    assert rollup.tool_calls_dev == 1
    assert rollup.tool_calls_pm == 1
    assert rollup.estimated_usd == pytest.approx(0.01)


def test_baseline_comparison_deviation():
    rollup = CostRollup(
        days=7,
        input_tokens=100_000,
        output_tokens=20_000,
        estimated_usd=2.0,
    )
    baseline = {
        "actual_usd": 2.5,
        "actual_input_tokens": 80_000,
        "actual_output_tokens": 25_000,
    }
    cmp_ = compare_to_baseline(rollup, baseline)
    assert cmp_["has_baseline"] is True
    assert cmp_["usd_deviation_pct"] == pytest.approx(-20.0)
    assert cmp_["input_token_deviation_pct"] == pytest.approx(25.0)
    assert cmp_["output_token_deviation_pct"] == pytest.approx(-20.0)


def test_save_and_load_baseline():
    save_baseline({"actual_usd": 9.99, "period_note": "test week"})
    loaded = load_baseline()
    assert loaded["actual_usd"] == 9.99
    assert "updated_at" in loaded


def test_format_rollup_includes_baseline():
    today = date.today()
    _write_events(today, [{"kind": "llm", "input_tokens": 500, "output_tokens": 100, "estimated_usd": 0.05}])
    save_baseline({"actual_usd": 0.10, "period_note": "MiniMax"})
    lines = format_rollup_lines()
    text = "\n".join(lines)
    assert "成本标定" in text
    assert "账单对照" in text
    assert "USD 偏差" in text


def test_cost_tracker_emits_events():
    today = date.today()
    sk = "test-session-cal"
    reset_session_cost(sk)
    cost = get_session_cost(sk)
    cost.record_llm_call(input_tokens=100, output_tokens=50, model="deepseek-chat")
    cost.record_tool_call("memo_search")
    cost.record_tool_call("delegate_task")
    path = events_path_for(today)
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 3
    kinds = [json.loads(ln)["kind"] for ln in lines]
    assert kinds.count("llm") >= 1
    assert kinds.count("tool") >= 2


def test_format_cost_with_calibration():
    sk = "fmt-session"
    reset_session_cost(sk)
    get_session_cost(sk).record_llm_call(input_tokens=10, output_tokens=5)
    text = format_cost_with_calibration(sk)
    assert "会话成本概览" in text
    assert "成本标定" in text
