"""Tests for compaction audit sampling (P5)."""

from __future__ import annotations

import json

from butler.ops.compaction_audit import (
    collect_compaction_samples,
    format_audit_report,
    run_audit,
)


def test_collect_compaction_samples_pairs_scheduled_done(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_TRANSCRIPT", "1")
    sk = "wechat:audit:test"
    from butler.core.session_transcript import (
        record_compact_done,
        record_compact_scheduled,
        transcript_path,
    )

    record_compact_scheduled(sk, messages_before=40, tokens_estimated=50000)
    record_compact_done(sk, messages_after=12, tokens_after=15000, summary_chars=800)

    samples = collect_compaction_samples(sk)
    assert len(samples) >= 2
    done = [s for s in samples if s.event_type == "compact_done"][-1]
    assert done.tokens_before == 50000
    assert done.tokens_after == 15000
    assert done.messages_before == 40
    assert done.messages_after == 12
    assert done.token_reduction_pct is not None
    assert done.token_reduction_pct > 0


def test_format_audit_report():
    from butler.ops.compaction_audit import CompactionAuditSample

    text = format_audit_report(
        "sk1",
        [
            CompactionAuditSample(
                session_key="sk1",
                ts="2026-06-29T12:00:00+00:00",
                event_type="compact_done",
                source="context",
                tokens_before=1000,
                tokens_after=400,
                messages_before=20,
                messages_after=8,
                summary_chars=120,
                token_reduction_pct=60.0,
                checkpoint_preview_len=None,
            ),
        ],
    )
    assert "压缩审计" in text
    assert "1000→400" in text


def test_run_audit_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    out = run_audit()
    assert "无含 compact_done" in out or "compact" in out.lower()
