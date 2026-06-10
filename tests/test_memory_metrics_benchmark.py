"""Tests for memory effectiveness metrics (L2) and benchmark framework (L3).

Coverage:
  - MemoryMetricsCollector lifecycle
  - SessionMemoryMetrics computed properties
  - AggregateMemoryMetrics
  - Persistence (save/load)
  - Facade integration (write/recall emit events)
  - BenchmarkRunner (MB1-MB7)
  - memory_metrics tool
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


# ===========================================================================
# L2: Memory Metrics Collector
# ===========================================================================


class TestMemoryMetricsCollector:
    """MemoryMetricsCollector singleton and event lifecycle."""

    def setup_method(self):
        from butler.memory.memory_metrics import MemoryMetricsCollector

        MemoryMetricsCollector.reset()

    def test_singleton(self):
        from butler.memory.memory_metrics import get_collector

        c1 = get_collector()
        c2 = get_collector()
        assert c1 is c2

    def test_session_lifecycle(self):
        from butler.memory.memory_metrics import get_collector

        c = get_collector()
        c.start_session("s1")
        c.on_write("owner_profile", True)
        c.on_write("owner_experience", True)
        c.on_write("owner_profile", False)
        c.on_recall("experience", "test", 3)
        c.on_prefetch("query", True, 2)
        c.on_prefetch("query2", False, 0)

        m = c.get_session_metrics("s1")
        assert m["writes"] == 3
        assert m["writes_successful"] == 2
        assert m["recalls"] == 1
        assert m["recalls_with_hits"] == 1
        assert m["prefetch_turns"] == 2
        assert m["prefetch_hits"] == 1

    def test_computed_properties(self):
        from butler.memory.memory_metrics import SessionMemoryMetrics

        m = SessionMemoryMetrics(session_id="t")
        m.writes = 10
        m.writes_successful = 8
        m.prefetch_turns = 20
        m.prefetch_hits = 15
        m.facts_pre_compact = 40
        m.facts_post_compact = 35
        m.decay_evaluations = 100
        m.decay_false_kills = 5

        assert abs(m.write_survival_rate - 0.8) < 1e-6
        assert abs(m.first_turn_hit_rate - 0.75) < 1e-6
        assert abs(m.fact_survival_rate - 0.875) < 1e-6
        assert abs(m.decay_error_rate - 0.05) < 1e-6

    def test_zero_division_safe(self):
        from butler.memory.memory_metrics import SessionMemoryMetrics

        m = SessionMemoryMetrics()
        assert m.write_survival_rate == 1.0
        assert m.first_turn_hit_rate == 1.0
        assert m.fact_survival_rate == 1.0
        assert m.decay_error_rate == 0.0

    def test_aggregate(self):
        from butler.memory.memory_metrics import get_collector

        c = get_collector()
        c.start_session("a")
        c.on_write("p", True)
        c.on_write("p", True)

        c.start_session("b")
        c.on_write("p", False)

        agg = c.get_aggregate()
        assert agg.total_sessions == 2
        assert agg.total_writes == 3
        assert agg.total_writes_successful == 2

    def test_persistence(self, tmp_path: Path):
        from butler.memory.memory_metrics import MemoryMetricsCollector, get_collector

        c = get_collector()
        c.start_session("persist")
        c.on_write("p", True)
        c.on_recall("e", "q", 5)

        path = tmp_path / "metrics.json"
        c.save_to_file(path)
        assert path.is_file()

        MemoryMetricsCollector.reset()
        c2 = get_collector()
        c2.load_from_file(path)

        m = c2.get_session_metrics("persist")
        assert m["writes"] == 1
        assert m["recalls"] == 1

    def test_fact_extraction_event(self):
        from butler.memory.memory_metrics import get_collector

        c = get_collector()
        c.start_session("fact")
        c.on_fact_extraction(pre_count=40, post_count=35)

        m = c.get_session_metrics("fact")
        assert m["facts_pre_compact"] == 40
        assert m["facts_post_compact"] == 35
        assert abs(m["computed"]["fact_survival_rate"] - 0.875) < 1e-3

    def test_decay_evaluation_event(self):
        from butler.memory.memory_metrics import get_collector

        c = get_collector()
        c.start_session("decay")
        c.on_decay_evaluation(total_important=50, killed=3)

        m = c.get_session_metrics("decay")
        assert m["decay_evaluations"] == 50
        assert m["decay_false_kills"] == 3
        assert abs(m["computed"]["decay_error_rate"] - 0.06) < 1e-3


# ===========================================================================
# L3: Memory Benchmark Framework
# ===========================================================================


class TestMemoryBenchmark:
    """Benchmark tasks MB1-MB7."""

    def test_mb1_exact_recall(self):
        from butler.memory.memory_benchmark import _run_mb1_exact_recall

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            (home / "tenants" / "default" / "memory").mkdir(parents=True)
            result = _run_mb1_exact_recall(home)
            assert result.benchmark_id == "MB1"
            assert result.passed is True
            assert result.score == 1.0

    def test_mb2_semantic_recall(self):
        from butler.memory.memory_benchmark import _run_mb2_semantic_recall

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            (home / "tenants" / "default" / "memory").mkdir(parents=True)
            result = _run_mb2_semantic_recall(home)
            assert result.benchmark_id == "MB2"
            assert result.passed is True

    def test_mb3_cross_session_persistence(self):
        from butler.memory.memory_benchmark import _run_mb3_cross_session_persistence

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            (home / "tenants" / "default" / "memory").mkdir(parents=True)
            result = _run_mb3_cross_session_persistence(home)
            assert result.benchmark_id == "MB3"
            assert result.passed is True

    def test_mb4_decay_behavior(self):
        from butler.memory.memory_benchmark import _run_mb4_decay_behavior

        result = _run_mb4_decay_behavior(Path("/dev/null"))
        assert result.benchmark_id == "MB4"
        assert result.passed is True

    def test_mb5_capacity_pressure(self):
        from butler.memory.memory_benchmark import _run_mb5_capacity_pressure

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            (home / "tenants" / "default" / "memory").mkdir(parents=True)
            result = _run_mb5_capacity_pressure(home)
            assert result.benchmark_id == "MB5"
            assert result.passed is True

    def test_mb6_fact_compaction(self):
        from butler.memory.memory_benchmark import _run_mb6_fact_compaction

        result = _run_mb6_fact_compaction(Path("/dev/null"))
        assert result.benchmark_id == "MB6"
        assert result.passed is True

    def test_mb7_injection_safety(self):
        from butler.memory.memory_benchmark import _run_mb7_injection_safety

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            (home / "tenants" / "default" / "memory").mkdir(parents=True)
            result = _run_mb7_injection_safety(home)
            assert result.benchmark_id == "MB7"
            assert result.passed is True

    def test_run_all_benchmarks(self):
        from butler.memory.memory_benchmark import run_benchmarks

        report = run_benchmarks()
        assert report.total == 7
        assert report.passed >= 5  # allow some variance
        summary = report.summary()
        assert summary["total"] == 7


# ===========================================================================
# Tool integration
# ===========================================================================


class TestMemoryMetricsTool:
    """memory_metrics tool handler tests."""

    def setup_method(self):
        from butler.memory.memory_metrics import MemoryMetricsCollector

        MemoryMetricsCollector.reset()

    def test_tool_summary(self):
        from butler.tools.memory_tools import tool_memory_metrics

        result = json.loads(tool_memory_metrics(detail="summary"))
        assert "total_sessions" in result
        assert "computed" in result

    def test_tool_session_no_data(self):
        from butler.tools.memory_tools import tool_memory_metrics

        result = json.loads(tool_memory_metrics(detail="session", session_id="none"))
        assert "error" in result

    def test_tool_benchmark(self):
        from butler.tools.memory_tools import tool_memory_metrics

        result = json.loads(tool_memory_metrics(detail="benchmark"))
        assert result["total"] == 7

    def test_tool_registered(self):
        """memory_metrics tool must be in register_memory_tools."""
        registered = {}

        def mock_register(name, **kwargs):
            registered[name] = kwargs

        from butler.tools.memory_tools import register_memory_tools

        register_memory_tools(mock_register)
        assert "memory_metrics" in registered
        assert "butler_remember" in registered
        assert "butler_recall" in registered
