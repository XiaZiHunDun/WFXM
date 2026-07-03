"""DevEngine / SWE-bench / B9 benchmarks → LangFuse evaluation datasets.

Converts B1–B8 dev benchmark results, SWE-bench Lite instances, and B9 delegate
task specs into LangFuse Dataset items. Used by ``eval_regression`` ``--sync-dataset``.

Usage::

    from butler.ops.dev_eval import sync_all_eval_datasets
    summary = sync_all_eval_datasets(dev_report=dev, mem_report=mem)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DATASET_NAME_DEV = "butler-dev-benchmark"
DATASET_NAME_SWEBENCH = "butler-swebench-lite"
DATASET_NAME_B9 = "butler-llm-delegate-benchmark"
DATASET_NAME_CK = "butler-coding-knowledge-benchmark"


def dev_benchmark_to_dataset_items(report: Any) -> list[Any]:
    """Convert a DevEngine BenchmarkReport into LangFuse DatasetItems."""
    from butler.ops.eval_bridge import DatasetItem

    items: list[DatasetItem] = []
    for r in getattr(report, "results", []):
        expected = getattr(r, "expected", None)
        items.append(DatasetItem(
            input={
                "task_id": r.task_id,
                "category": r.category.value if hasattr(r.category, "value") else str(r.category),
                "description": r.description,
            },
            expected_output={
                "outcome": (
                    expected.outcome.value
                    if expected and hasattr(expected.outcome, "value")
                    else str(getattr(expected, "outcome", "DONE"))
                ),
                "max_iterations": getattr(expected, "max_iterations", 20),
                "max_edits": getattr(expected, "max_edits", 5),
                "expect_first_pass": getattr(expected, "expect_first_pass", False),
                "expect_fix_loop": getattr(expected, "expect_fix_loop", False),
            },
            metadata={
                "passed": r.passed,
                "failure_reasons": getattr(r, "failure_reasons", [])[:3],
                "elapsed_seconds": getattr(r, "elapsed_seconds", 0.0),
            },
            source_id=r.task_id,
        ))
    return items


def swebench_instances_to_dataset_items() -> list[Any]:
    """Build DatasetItems from static SWE-bench Lite instance definitions."""
    from butler.dev_engine.swebench_lite import get_all_instances
    from butler.ops.eval_bridge import DatasetItem

    items: list[DatasetItem] = []
    for inst in get_all_instances():
        items.append(DatasetItem(
            input={
                "instance_id": inst.instance_id,
                "category": inst.category,
                "repo_name": inst.repo_name,
                "issue_title": inst.issue_title,
                "issue_body": inst.issue_body,
            },
            expected_output={
                "oracle_patch_files": list(inst.oracle_patch.keys()),
                "difficulty": inst.difficulty,
                "tags": inst.tags,
            },
            metadata={
                "file_count": len(inst.files),
            },
            source_id=inst.instance_id,
        ))
    return items


def b9_tasks_to_dataset_items() -> list[Any]:
    """Build DatasetItems from B9 delegate task specifications."""
    from butler.dev_engine.llm_delegate_benchmark import B9_TASKS
    from butler.ops.eval_bridge import DatasetItem

    items: list[DatasetItem] = []
    for spec in B9_TASKS:
        items.append(DatasetItem(
            input={
                "task_id": spec.task_id,
                "description": spec.description,
                "delegate_prompt": spec.delegate_prompt,
            },
            expected_output={
                "mode": "oracle_apply_then_verify",
                "expect_pass": spec.expect_pass,
            },
            metadata={"tags": list(spec.tags)},
            source_id=spec.task_id,
        ))
    return items


def push_dev_benchmark_dataset(report: Any) -> dict[str, Any]:
    """Push B1–B8 dev benchmark definitions/results as a LangFuse dataset."""
    from butler.ops.eval_bridge import create_dataset, push_dataset_items

    summary: dict[str, Any] = {
        "dataset": DATASET_NAME_DEV,
        "dataset_items": 0,
        "dataset_created": False,
        "errors": [],
    }

    ds_id = create_dataset(DATASET_NAME_DEV, "Butler DevEngine benchmark B1–B8")
    if ds_id:
        summary["dataset_created"] = True

    items = dev_benchmark_to_dataset_items(report)
    ds_report = push_dataset_items(DATASET_NAME_DEV, items)
    summary["dataset_items"] = ds_report.dataset_items_pushed
    summary["errors"] = ds_report.errors
    return summary


def push_swebench_dataset() -> dict[str, Any]:
    """Push SWE-bench Lite instance catalog as a LangFuse dataset."""
    from butler.ops.eval_bridge import create_dataset, push_dataset_items

    summary: dict[str, Any] = {
        "dataset": DATASET_NAME_SWEBENCH,
        "dataset_items": 0,
        "dataset_created": False,
        "errors": [],
    }

    ds_id = create_dataset(
        DATASET_NAME_SWEBENCH,
        "Butler SWE-bench Lite adapted instances (SWE-001…015)",
    )
    if ds_id:
        summary["dataset_created"] = True

    items = swebench_instances_to_dataset_items()
    ds_report = push_dataset_items(DATASET_NAME_SWEBENCH, items)
    summary["dataset_items"] = ds_report.dataset_items_pushed
    summary["errors"] = ds_report.errors
    return summary


def push_b9_dataset() -> dict[str, Any]:
    """Push B9 LLM delegate task specs as a LangFuse dataset."""
    from butler.ops.eval_bridge import create_dataset, push_dataset_items

    summary: dict[str, Any] = {
        "dataset": DATASET_NAME_B9,
        "dataset_items": 0,
        "dataset_created": False,
        "errors": [],
    }

    ds_id = create_dataset(
        DATASET_NAME_B9,
        "Butler B9 LLM delegate benchmark tasks",
    )
    if ds_id:
        summary["dataset_created"] = True

    items = b9_tasks_to_dataset_items()
    ds_report = push_dataset_items(DATASET_NAME_B9, items)
    summary["dataset_items"] = ds_report.dataset_items_pushed
    summary["errors"] = ds_report.errors
    return summary


def coding_knowledge_to_dataset_items() -> list[Any]:
    """Build DatasetItems from CK1–CK10 coding knowledge cases."""
    from butler.dev_engine.coding_knowledge_benchmark import CK_CASES, run_coding_knowledge_benchmark
    from butler.ops.eval_bridge import DatasetItem

    report = run_coding_knowledge_benchmark()
    by_id = {r.case_id: r for r in report.results}
    items: list[DatasetItem] = []
    for case in CK_CASES:
        r = by_id.get(case.case_id)
        items.append(DatasetItem(
            input={
                "case_id": case.case_id,
                "theorem_id": case.theorem_id,
                "description": case.description,
                "bad_code": case.bad_code,
            },
            expected_output={
                "theorem_id": case.theorem_id,
                "bad_should_fail": True,
                "good_should_pass": True,
                "good_code": case.good_code,
            },
            metadata={
                "passed": r.passed if r else False,
                "bad_message": r.bad_message if r else "",
                "good_message": r.good_message if r else "",
            },
            source_id=case.case_id,
        ))
    return items


def push_coding_knowledge_dataset() -> dict[str, Any]:
    """Push T01–T10 coding knowledge benchmark as a LangFuse dataset."""
    from butler.ops.eval_bridge import create_dataset, push_dataset_items

    summary: dict[str, Any] = {
        "dataset": DATASET_NAME_CK,
        "dataset_items": 0,
        "dataset_created": False,
        "errors": [],
    }
    ds_id = create_dataset(
        DATASET_NAME_CK,
        "Butler coding knowledge T01–T10 advisory checker benchmark",
    )
    if ds_id:
        summary["dataset_created"] = True
    items = coding_knowledge_to_dataset_items()
    ds_report = push_dataset_items(DATASET_NAME_CK, items)
    summary["dataset_items"] = ds_report.dataset_items_pushed
    summary["errors"] = ds_report.errors
    return summary


def sync_all_eval_datasets(
    *,
    dev_report: Any | None = None,
    mem_report: Any | None = None,
    include_wechat: bool = True,
    include_memory: bool = True,
    include_dev: bool = True,
    include_swebench: bool = True,
    include_b9: bool = True,
    include_coding_knowledge: bool = True,
) -> dict[str, Any]:
    """Sync all evaluation datasets to LangFuse.

    When *dev_report* / *mem_report* are omitted, runs the corresponding benchmarks.
    """
    summary: dict[str, Any] = {
        "datasets": {},
        "total_items": 0,
        "any_pushed": False,
        "errors": [],
    }

    from butler.ops.dev_eval_ops import run_dataset_sync_safe

    if include_wechat:
        def _sync_wechat() -> tuple[dict[str, Any], int]:
            from butler.ops.wechat_dataset import load_and_push_wechat_dataset

            wx = load_and_push_wechat_dataset()
            items = int(wx.get("single_turn_items") or 0) + int(wx.get("multi_turn_items") or 0)
            return wx, items

        payload, wx_items, err = run_dataset_sync_safe("wechat", _sync_wechat)
        if payload is not None:
            summary["datasets"]["wechat"] = payload
            summary["total_items"] += wx_items
            if wx_items:
                summary["any_pushed"] = True
        if err:
            summary["errors"].append(err)

    if include_memory:
        def _sync_memory() -> tuple[dict[str, Any], int]:
            from butler.ops.memory_eval import (
                push_memory_benchmark_dataset,
                run_and_push_memory_eval,
            )

            if mem_report is None:
                mem_push = run_and_push_memory_eval()
            else:
                mem_push = push_memory_benchmark_dataset(mem_report)
            return mem_push, int(mem_push.get("dataset_items") or 0)

        payload, mem_items, err = run_dataset_sync_safe("memory", _sync_memory)
        if payload is not None:
            summary["datasets"]["memory"] = payload
            summary["total_items"] += mem_items
            if mem_items:
                summary["any_pushed"] = True
        if err:
            summary["errors"].append(err)

    if include_dev:
        def _sync_dev() -> tuple[dict[str, Any], int]:
            report = dev_report
            if report is None:
                from butler.dev_engine.dev_benchmark import run_benchmarks

                report = run_benchmarks()
            dev_push = push_dev_benchmark_dataset(report)
            return dev_push, int(dev_push.get("dataset_items") or 0)

        payload, dev_items, err = run_dataset_sync_safe("dev", _sync_dev)
        if payload is not None:
            summary["datasets"]["dev"] = payload
            summary["total_items"] += dev_items
            if dev_items:
                summary["any_pushed"] = True
        if err:
            summary["errors"].append(err)

    if include_swebench:
        def _sync_swebench() -> tuple[dict[str, Any], int]:
            swe_push = push_swebench_dataset()
            return swe_push, int(swe_push.get("dataset_items") or 0)

        payload, swe_items, err = run_dataset_sync_safe("swebench", _sync_swebench)
        if payload is not None:
            summary["datasets"]["swebench"] = payload
            summary["total_items"] += swe_items
            if swe_items:
                summary["any_pushed"] = True
        if err:
            summary["errors"].append(err)

    if include_b9:
        def _sync_b9() -> tuple[dict[str, Any], int]:
            b9_push = push_b9_dataset()
            return b9_push, int(b9_push.get("dataset_items") or 0)

        payload, b9_items, err = run_dataset_sync_safe("b9", _sync_b9)
        if payload is not None:
            summary["datasets"]["b9"] = payload
            summary["total_items"] += b9_items
            if b9_items:
                summary["any_pushed"] = True
        if err:
            summary["errors"].append(err)

    if include_coding_knowledge:
        def _sync_ck() -> tuple[dict[str, Any], int]:
            ck_push = push_coding_knowledge_dataset()
            return ck_push, int(ck_push.get("dataset_items") or 0)

        payload, ck_items, err = run_dataset_sync_safe("coding_knowledge", _sync_ck)
        if payload is not None:
            summary["datasets"]["coding_knowledge"] = payload
            summary["total_items"] += ck_items
            if ck_items:
                summary["any_pushed"] = True
        if err:
            summary["errors"].append(err)

    return summary


__all__ = [
    "DATASET_NAME_B9",
    "DATASET_NAME_CK",
    "DATASET_NAME_DEV",
    "DATASET_NAME_SWEBENCH",
    "b9_tasks_to_dataset_items",
    "coding_knowledge_to_dataset_items",
    "dev_benchmark_to_dataset_items",
    "push_b9_dataset",
    "push_coding_knowledge_dataset",
    "push_dev_benchmark_dataset",
    "push_swebench_dataset",
    "swebench_instances_to_dataset_items",
    "sync_all_eval_datasets",
]
