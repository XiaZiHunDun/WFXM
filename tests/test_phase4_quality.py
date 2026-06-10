"""Tests for Phase 4 quality evolution:
  - 4.1: Experience mining
  - 4.2: Smart forget (type-based decay)
  - 4.3: P_r/R_r retrieval precision/recall metrics
"""

from __future__ import annotations

import math
import tempfile
import time
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from butler.memory.retrieval_ranking import (
    MEMORY_TYPE_HALF_LIFE_MULTIPLIER,
    type_adjusted_half_life,
    decay_factor,
    rerank_memory_hits,
)
from butler.memory.experience_mining import (
    CandidateExperience,
    MiningReport,
    mine_workspace_patterns,
    mine_recent_edits,
    run_mining,
)
from butler.memory.memory_metrics import (
    MemoryMetricsCollector,
    SessionMemoryMetrics,
    get_collector,
)


# ── 4.2: Smart Forget (Type-Based Decay) ──


class TestSmartForget:
    def test_permanent_types_no_decay(self):
        for mem_type in ["profile", "birthday", "identity", "preference", "permanent"]:
            half = type_adjusted_half_life(30.0, mem_type)
            assert half == float("inf"), f"{mem_type} should have infinite half-life"

    def test_standard_types_normal_decay(self):
        half = type_adjusted_half_life(30.0, "experience")
        assert half == 30.0

    def test_ephemeral_types_fast_decay(self):
        half = type_adjusted_half_life(30.0, "conversation")
        assert half < 30.0
        assert half == pytest.approx(30.0 * 0.33, rel=0.01)

    def test_unknown_type_default_decay(self):
        half = type_adjusted_half_life(30.0, "unknown_type")
        assert half == 30.0

    def test_empty_type_default_decay(self):
        half = type_adjusted_half_life(30.0, "")
        assert half == 30.0

    def test_decay_factor_infinite_half_life(self):
        factor = decay_factor(365.0, half_life_days=float("inf"))
        assert factor == 1.0

    def test_permanent_memory_never_killed(self):
        ts = time.time()
        old_ts = ts - 365 * 86400  # 1 year ago
        hits = [{
            "score": 0.5,
            "created_at": old_ts,
            "memory_type": "birthday",
            "access_count": 0,
        }]
        with patch("butler.memory.retrieval_ranking.memory_half_life_days", return_value=30.0):
            result = rerank_memory_hits(hits, now=ts)
        assert result[0].get("decay_killed") is not True
        assert result[0]["rank_score"] > 0.3

    def test_ephemeral_memory_decays_faster(self):
        ts = time.time()
        old_ts = ts - 60 * 86400  # 60 days ago
        hits_exp = [{
            "score": 0.8,
            "created_at": old_ts,
            "memory_type": "experience",
            "access_count": 0,
        }]
        hits_eph = [{
            "score": 0.8,
            "created_at": old_ts,
            "memory_type": "conversation",
            "access_count": 0,
        }]
        with patch("butler.memory.retrieval_ranking.memory_half_life_days", return_value=30.0):
            r_exp = rerank_memory_hits(hits_exp, now=ts)
            r_eph = rerank_memory_hits(hits_eph, now=ts)
        assert r_eph[0]["rank_score"] < r_exp[0]["rank_score"]

    def test_all_multiplier_types_defined(self):
        assert len(MEMORY_TYPE_HALF_LIFE_MULTIPLIER) >= 10
        for key, val in MEMORY_TYPE_HALF_LIFE_MULTIPLIER.items():
            assert isinstance(val, (int, float))


# ── 4.1: Experience Mining ──


class TestExperienceMining:
    def test_candidate_experience_high_confidence(self):
        c = CandidateExperience(source="test", category="test", content="x", confidence=0.8)
        assert c.is_high_confidence

    def test_candidate_experience_low_confidence(self):
        c = CandidateExperience(source="test", category="test", content="x", confidence=0.3)
        assert not c.is_high_confidence

    def test_mining_report_summary(self):
        r = MiningReport(
            candidates=[
                CandidateExperience(source="a", category="a", content="a", confidence=0.8),
                CandidateExperience(source="b", category="b", content="b", confidence=0.3),
            ],
            sources_scanned=2,
        )
        s = r.summary()
        assert s["total_candidates"] == 2
        assert s["high_confidence"] == 1

    def test_mine_workspace_patterns(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")
        (tmp_path / "Dockerfile").write_text("FROM python:3.12")
        candidates = mine_workspace_patterns(tmp_path)
        assert len(candidates) == 2
        categories = {c.category for c in candidates}
        assert "dependency" in categories
        assert "deployment" in categories

    def test_mine_workspace_patterns_empty(self, tmp_path):
        candidates = mine_workspace_patterns(tmp_path)
        assert candidates == []

    def test_mine_recent_edits(self, tmp_path):
        (tmp_path / "hello.py").write_text("print('hi')")
        candidates = mine_recent_edits(tmp_path, days=1)
        assert len(candidates) >= 1
        assert candidates[0].category == "development_activity"

    def test_mine_recent_edits_skips_hidden(self, tmp_path):
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "secret.txt").write_text("secret")
        (tmp_path / "visible.py").write_text("ok")
        candidates = mine_recent_edits(tmp_path, days=1)
        sources = [c.source for c in candidates]
        assert not any(".hidden" in s for s in sources)

    def test_run_mining_full(self, tmp_path):
        (tmp_path / "Makefile").write_text("all:\n\techo hi")
        report = run_mining(workspace=tmp_path, days=7)
        assert report.sources_scanned >= 1
        assert len(report.candidates) >= 1
        assert report.elapsed_seconds >= 0

    def test_run_mining_no_workspace(self):
        report = run_mining(workspace=None)
        assert report.sources_scanned == 0


# ── 4.3: P_r/R_r Retrieval Metrics ──


class TestRetrievalMetrics:
    def setup_method(self):
        MemoryMetricsCollector.reset()

    def test_on_retrieval_tracking(self):
        c = get_collector()
        c.start_session("test")
        c.on_retrieval(total_returned=10, relevant=8, used_by_llm=5)
        m = c._current()
        assert m.retrieval_total == 10
        assert m.retrieval_relevant == 8
        assert m.retrieval_used_by_llm == 5

    def test_retrieval_precision(self):
        m = SessionMemoryMetrics(
            retrieval_total=10,
            retrieval_used_by_llm=7,
        )
        assert m.retrieval_precision == pytest.approx(0.7)

    def test_retrieval_precision_zero_total(self):
        m = SessionMemoryMetrics(retrieval_total=0)
        assert m.retrieval_precision == 1.0

    def test_retrieval_recall(self):
        m = SessionMemoryMetrics(
            retrieval_total=8,
            retrieval_relevant=10,
        )
        assert m.retrieval_recall == pytest.approx(0.8)

    def test_retrieval_recall_zero_relevant(self):
        m = SessionMemoryMetrics(retrieval_relevant=0)
        assert m.retrieval_recall == 1.0

    def test_metrics_to_dict_includes_pr_rr(self):
        c = get_collector()
        c.start_session("test")
        c.on_retrieval(total_returned=10, relevant=8, used_by_llm=6)
        d = c.get_session_metrics("test")
        assert "retrieval_total" in d
        assert "retrieval_relevant" in d
        assert "retrieval_used_by_llm" in d
        assert "retrieval_precision" in d["computed"]
        assert "retrieval_recall" in d["computed"]

    def test_multiple_retrieval_accumulates(self):
        c = get_collector()
        c.start_session("test")
        c.on_retrieval(total_returned=5, relevant=4, used_by_llm=3)
        c.on_retrieval(total_returned=5, relevant=4, used_by_llm=2)
        m = c._current()
        assert m.retrieval_total == 10
        assert m.retrieval_relevant == 8
        assert m.retrieval_used_by_llm == 5

    def test_no_session_noop(self):
        c = get_collector()
        c.on_retrieval(total_returned=10)  # should not crash
