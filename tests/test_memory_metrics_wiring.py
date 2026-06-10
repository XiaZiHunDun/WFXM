"""Tests for D2-4/D2-5 memory metrics wiring into production paths."""

from __future__ import annotations

import pytest

from butler.memory.memory_metrics import (
    MemoryMetricsCollector,
    SessionMemoryMetrics,
    get_collector,
)


@pytest.fixture(autouse=True)
def _reset_collector():
    MemoryMetricsCollector.reset()
    yield
    MemoryMetricsCollector.reset()


class TestSessionMemoryMetricsComputation:
    def test_write_survival_rate(self):
        m = SessionMemoryMetrics(session_id="t1")
        assert m.write_survival_rate == 1.0
        m.writes = 10
        m.writes_successful = 8
        assert m.write_survival_rate == 0.8

    def test_first_turn_hit_rate(self):
        m = SessionMemoryMetrics(session_id="t1")
        assert m.first_turn_hit_rate == 1.0
        m.prefetch_turns = 5
        m.prefetch_hits = 4
        assert m.first_turn_hit_rate == 0.8

    def test_fact_survival_rate(self):
        m = SessionMemoryMetrics(session_id="t1")
        assert m.fact_survival_rate == 1.0
        m.facts_pre_compact = 10
        m.facts_post_compact = 9
        assert m.fact_survival_rate == 0.9

    def test_decay_error_rate(self):
        m = SessionMemoryMetrics(session_id="t1")
        assert m.decay_error_rate == 0.0
        m.decay_evaluations = 20
        m.decay_false_kills = 2
        assert m.decay_error_rate == 0.1


class TestCollectorWiring:
    def test_start_session_creates_entry(self):
        c = get_collector()
        c.start_session("s1")
        metrics = c.get_session_metrics("s1")
        assert "error" not in metrics
        assert metrics["session_id"] == "s1"

    def test_on_write_increments(self):
        c = get_collector()
        c.start_session("s1")
        c.on_write("experience", success=True)
        c.on_write("experience", success=False)
        c.on_write("profile", success=True)
        m = c.get_session_metrics("s1")
        assert m["writes"] == 3
        assert m["writes_successful"] == 2
        assert m["computed"]["write_survival_rate"] == pytest.approx(2 / 3, abs=0.01)

    def test_on_prefetch_increments(self):
        c = get_collector()
        c.start_session("s1")
        c.on_prefetch("测试查询", hit=True, result_count=3)
        c.on_prefetch("空查询", hit=False, result_count=0)
        m = c.get_session_metrics("s1")
        assert m["prefetch_turns"] == 2
        assert m["prefetch_hits"] == 1
        assert m["computed"]["first_turn_hit_rate"] == 0.5

    def test_aggregate_across_sessions(self):
        c = get_collector()
        c.start_session("s1")
        c.on_write("exp", success=True)
        c.on_prefetch("q1", hit=True)
        c.start_session("s2")
        c.on_write("exp", success=True)
        c.on_write("exp", success=False)
        c.on_prefetch("q2", hit=False)
        agg = c.get_aggregate()
        assert agg.total_sessions == 2
        assert agg.total_writes == 3
        assert agg.total_writes_successful == 2
        assert agg.total_prefetch_turns == 2
        assert agg.total_prefetch_hits == 1

    def test_on_write_noop_without_session(self):
        c = get_collector()
        c.on_write("exp", success=True)
        agg = c.get_aggregate()
        assert agg.total_writes == 0

    def test_on_prefetch_noop_without_session(self):
        c = get_collector()
        c.on_prefetch("q", hit=True)
        agg = c.get_aggregate()
        assert agg.total_prefetch_turns == 0

    def test_to_dict_structure(self):
        c = get_collector()
        c.start_session("s1")
        c.on_write("exp", success=True)
        c.on_prefetch("q", hit=True, result_count=2)
        m = c.get_session_metrics("s1")
        assert "computed" in m
        assert "write_survival_rate" in m["computed"]
        assert "first_turn_hit_rate" in m["computed"]

    def test_write_survival_closed_loop(self):
        c = get_collector()
        c.start_session("s1")
        c.register_write_probe("灵文试点统一测试日是 2026-05-22", "project_notes")
        c.on_recall(
            "project",
            "测试日",
            1,
            hit_texts=["灵文试点统一测试日是 2026-05-22"],
        )
        m = c.get_session_metrics("s1")
        assert m["write_probes"] == 1
        assert m["write_probes_recalled"] == 1
        assert m["computed"]["write_survival_rate"] == 1.0

    def test_write_probe_skips_short_content(self):
        c = get_collector()
        c.start_session("s1")
        c.register_write_probe("短", "exp")
        m = c.get_session_metrics("s1")
        assert m["write_probes"] == 0

    def test_export_and_load_json(self, tmp_path):
        c = get_collector()
        c.start_session("s1")
        c.on_write("exp", success=True)
        c.on_prefetch("q", hit=True, result_count=3)

        path = tmp_path / "metrics.json"
        c.save_to_file(path)
        assert path.exists()

        MemoryMetricsCollector.reset()
        c2 = get_collector()
        c2.load_from_file(path)
        m = c2.get_session_metrics("s1")
        assert m["writes"] == 1
        assert m["prefetch_turns"] == 1
