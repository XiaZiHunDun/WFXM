"""Tests for butler.ops.dev_eval — dev / SWE / B9 → LangFuse datasets."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from butler.dev_engine.llm_delegate_benchmark import B9_TASKS
from butler.dev_engine.swebench_lite import get_all_instances
from butler.ops.dev_eval import (
    DATASET_NAME_B9,
    DATASET_NAME_DEV,
    DATASET_NAME_SWEBENCH,
    b9_tasks_to_dataset_items,
    dev_benchmark_to_dataset_items,
    push_b9_dataset,
    push_dev_benchmark_dataset,
    push_swebench_dataset,
    swebench_instances_to_dataset_items,
    sync_all_eval_datasets,
)


def _make_dev_result(task_id="b1_syntax_fix", category="syntax_fix", passed=True):
    return SimpleNamespace(
        task_id=task_id,
        category=SimpleNamespace(value=category),
        description=f"task {task_id}",
        passed=passed,
        failure_reasons=[],
        elapsed_seconds=0.1,
        expected=SimpleNamespace(
            outcome=SimpleNamespace(value="DONE"),
            max_iterations=6,
            max_edits=1,
            expect_first_pass=True,
            expect_fix_loop=False,
        ),
    )


def _make_dev_report(n=9):
    tasks = [
        ("b1_syntax_fix", "syntax_fix"),
        ("b2_logic_bug", "logic_bug"),
        ("b3_add_function", "add_function"),
        ("b4_refactor", "refactor"),
        ("b5_fix_test", "fix_test"),
        ("b6_impossible", "impossible"),
        ("b7_rollback", "rollback"),
        ("B8_swebench_lite", "logic_bug"),
        ("b10_verify_layers", "verify_layered"),
    ]
    results = [
        _make_dev_result(task_id=tid, category=cat)
        for tid, cat in tasks[:n]
    ]
    return SimpleNamespace(results=results)


def test_dev_benchmark_to_dataset_items():
    report = _make_dev_report()
    items = dev_benchmark_to_dataset_items(report)
    assert len(items) == 9
    assert items[0].input["task_id"] == "b1_syntax_fix"
    assert items[0].source_id == "b1_syntax_fix"
    assert items[0].expected_output["max_iterations"] == 6


def test_swebench_instances_to_dataset_items():
    items = swebench_instances_to_dataset_items()
    instances = get_all_instances()
    assert len(items) == len(instances)
    assert items[0].input["instance_id"].startswith("SWE-")
    assert items[0].expected_output["oracle_patch_files"]


def test_b9_tasks_to_dataset_items():
    items = b9_tasks_to_dataset_items()
    assert len(items) == len(B9_TASKS)
    assert items[0].input["delegate_prompt"]
    assert items[0].source_id == B9_TASKS[0].task_id


@patch("butler.ops.eval_bridge.create_dataset", return_value="ds-1")
@patch("butler.ops.eval_bridge.push_dataset_items")
def test_push_dev_benchmark_dataset(mock_push, mock_create):
    from butler.ops.eval_bridge import EvalReport

    mock_push.return_value = EvalReport(dataset_items_pushed=8)
    summary = push_dev_benchmark_dataset(_make_dev_report())
    assert summary["dataset"] == DATASET_NAME_DEV
    assert summary["dataset_items"] == 8
    assert summary["dataset_created"] is True
    mock_create.assert_called_once_with(DATASET_NAME_DEV, "Butler DevEngine benchmark B1–B8")


@patch("butler.ops.eval_bridge.create_dataset", return_value="ds-2")
@patch("butler.ops.eval_bridge.push_dataset_items")
def test_push_swebench_dataset(mock_push, mock_create):
    from butler.ops.eval_bridge import EvalReport

    mock_push.return_value = EvalReport(dataset_items_pushed=15)
    summary = push_swebench_dataset()
    assert summary["dataset"] == DATASET_NAME_SWEBENCH
    assert summary["dataset_items"] == 15
    mock_create.assert_called_once()


@patch("butler.ops.eval_bridge.create_dataset", return_value="ds-3")
@patch("butler.ops.eval_bridge.push_dataset_items")
def test_push_b9_dataset(mock_push, mock_create):
    from butler.ops.eval_bridge import EvalReport

    mock_push.return_value = EvalReport(dataset_items_pushed=len(B9_TASKS))
    summary = push_b9_dataset()
    assert summary["dataset"] == DATASET_NAME_B9
    assert summary["dataset_items"] == len(B9_TASKS)


@patch("butler.ops.dev_eval.push_coding_knowledge_dataset")
@patch("butler.ops.dev_eval.push_b9_dataset")
@patch("butler.ops.dev_eval.push_swebench_dataset")
@patch("butler.ops.dev_eval.push_dev_benchmark_dataset")
@patch("butler.ops.memory_eval.push_memory_benchmark_dataset")
@patch("butler.ops.wechat_dataset.load_and_push_wechat_dataset")
def test_sync_all_eval_datasets_reuses_reports(
    mock_wechat,
    mock_mem,
    mock_dev,
    mock_swe,
    mock_b9,
    mock_ck,
):
    dev_report = _make_dev_report()
    mem_report = SimpleNamespace(results=[])

    mock_wechat.return_value = {"single_turn_items": 3, "multi_turn_items": 2}
    mock_mem.return_value = {"dataset_items": 7}
    mock_dev.return_value = {"dataset_items": 8}
    mock_swe.return_value = {"dataset_items": 15}
    mock_b9.return_value = {"dataset_items": len(B9_TASKS)}
    mock_ck.return_value = {"dataset_items": 10}

    summary = sync_all_eval_datasets(dev_report=dev_report, mem_report=mem_report)

    assert summary["any_pushed"] is True
    assert summary["total_items"] == 3 + 2 + 7 + 8 + 15 + len(B9_TASKS) + 10
    mock_dev.assert_called_once_with(dev_report)
    mock_mem.assert_called_once_with(mem_report)
    mock_swe.assert_called_once()
    mock_b9.assert_called_once()
