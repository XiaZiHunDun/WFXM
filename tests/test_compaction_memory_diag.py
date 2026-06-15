"""Compaction + fact anchor diagnostics for /诊断 (S_f wiring)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from butler.core.compaction_status import format_fact_survival_line, promote_compaction_diagnostics_to_health
from butler.core.fact_extraction import record_fact_anchor_metrics, save_facts
from butler.core.post_compact_cleanup import build_post_compact_anchor_text
from butler.memory.memory_metrics import MemoryMetricsCollector, get_collector


@pytest.fixture(autouse=True)
def _reset_metrics():
    MemoryMetricsCollector.reset()
    yield
    MemoryMetricsCollector.reset()


def test_record_fact_anchor_metrics_updates_collector(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_FACT_EXTRACTION", "1")
    get_collector().start_session("wechat:u1:proj")
    save_facts(
        "wechat:u1:proj",
        [{"type": "decision", "value": f"fact-{i}", "ts": 1.0} for i in range(12)],
    )
    diag: dict = {}
    store, anchor = record_fact_anchor_metrics("wechat:u1:proj", diagnostics=diag)
    assert store == 12
    assert anchor == 12
    assert diag["fact_survival_rate_turn"] == 1.0
    mm = get_collector().get_session_metrics("wechat:u1:proj")
    assert mm["anchor_facts_pre"] == 12
    assert mm["anchor_facts_post"] == 12
    assert mm["computed"]["anchor_fact_survival_rate"] == 1.0


def test_build_post_compact_anchor_records_fact_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_FACT_EXTRACTION", "1")
    sk = "wechat:u1:proj"
    get_collector().start_session(sk)
    save_facts(sk, [{"type": "decision", "value": "使用 pytest", "ts": 1.0}])
    diag: dict = {}
    monkeypatch.setattr(
        "butler.execution_context.get_current_orchestrator",
        lambda: None,
    )
    monkeypatch.setattr(
        "butler.execution_context.get_current_session_key",
        lambda: sk,
    )
    monkeypatch.setattr(
        "butler.execution_context.get_audit_session_key",
        lambda fallback="_global": sk,
    )
    text = build_post_compact_anchor_text(diag)
    assert "会话关键事实" in text
    assert diag.get("post_compact_facts") is True
    assert diag.get("facts_store_count") == 1
    assert diag.get("facts_anchor_count") == 1


def test_format_fact_survival_line_turn_level():
    line = format_fact_survival_line(
        {"facts_store_count": 10, "facts_anchor_count": 8, "fact_survival_rate_turn": 0.8}
    )
    assert "事实锚点" in line
    assert "10" in line
    assert "8" in line


def test_promote_compaction_diagnostics_to_health():
    health: dict = {}
    promote_compaction_diagnostics_to_health(
        health,
        {
            "compaction_phase": "pre_turn",
            "facts_store_count": 5,
            "hygiene_compressed": True,
            "unrelated": 1,
        },
    )
    assert health["compaction_phase"] == "pre_turn"
    assert health["facts_store_count"] == 5
    assert health["hygiene_compressed"] is True
    assert "unrelated" not in health
