"""Tests for coding knowledge T01–T10 benchmark."""

from __future__ import annotations

from butler.dev_engine.coding_knowledge_benchmark import (
    CK_CASES,
    run_coding_knowledge_benchmark,
)
from butler.ops.dev_eval import coding_knowledge_to_dataset_items, push_coding_knowledge_dataset


class TestCodingKnowledgeBenchmark:
    def test_all_theorems_covered(self):
        ids = {c.theorem_id for c in CK_CASES}
        assert ids == {f"T{i:02d}" for i in range(1, 11)}

    def test_benchmark_all_pass(self):
        report = run_coding_knowledge_benchmark()
        assert report.total == len(CK_CASES)
        assert report.passed == report.total
        assert report.pass_rate == 1.0

    def test_dataset_items_shape(self):
        items = coding_knowledge_to_dataset_items()
        assert len(items) == len(CK_CASES)
        assert items[0].input["theorem_id"].startswith("T")
        assert items[0].expected_output["bad_should_fail"] is True

    def test_push_coding_knowledge_dataset_mock(self):
        summary = push_coding_knowledge_dataset()
        assert summary["dataset"] == "butler-coding-knowledge-benchmark"
        assert summary["dataset_items"] == 0 or summary["dataset_items"] == len(CK_CASES)
