"""Outbound inter-chunk delay helper."""

from __future__ import annotations

from butler.gateway.outbound_delay import inter_chunk_delay_seconds, outbound_block_delay_ms


def test_fallback_when_unset(monkeypatch):
    monkeypatch.delenv("BUTLER_OUTBOUND_BLOCK_DELAY_MS", raising=False)
    assert inter_chunk_delay_seconds(fallback_seconds=1.5) == 1.5


def test_random_ms_range(monkeypatch):
    monkeypatch.setenv("BUTLER_OUTBOUND_BLOCK_DELAY_MS", "1000")
    assert outbound_block_delay_ms() == 1000
    d = inter_chunk_delay_seconds(fallback_seconds=0.0)
    assert 0.5 <= d <= 1.5
