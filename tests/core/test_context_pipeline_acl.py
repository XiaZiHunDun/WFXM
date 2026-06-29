"""Integration: ContextPipeline consumes ACL-adapted compaction summary."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.core.context_pipeline import ContextPipeline
from butler.core.loop_types import LoopConfig


@pytest.mark.unit
@patch("butler.core.context_pipeline.compress_messages")
def test_compress_context_adapts_v2_summary_dict(mock_compress):
    cfg = LoopConfig(max_context_tokens=128000)
    pipe = ContextPipeline(cfg)
    msgs = [{"role": "user", "content": "hi"}] * 20
    mock_compress.return_value = (
        msgs[:5],
        {"summary": "会话摘要", "tags": ["tcr", "gateway"]},
        True,
    )
    diag: dict = {}
    out = pipe.compress_context(msgs, diagnostics=diag)
    assert len(out) <= len(msgs)
    assert "会话摘要" in pipe.compression_summary
    assert "tcr" in pipe.compression_summary
    assert diag.get("compaction_view_version") == "v1"
    assert diag.get("compaction_acl_shape") == "v2_summary_tags"


@pytest.mark.unit
@patch("butler.core.context_pipeline.compress_messages")
def test_compress_context_string_summary_unchanged_semantics(mock_compress):
    cfg = LoopConfig(max_context_tokens=128000)
    pipe = ContextPipeline(cfg)
    msgs = [{"role": "user", "content": "x"}] * 15
    mock_compress.return_value = (msgs[:4], "plain summary", True)
    pipe.compress_context(msgs)
    assert pipe.compression_summary == "plain summary"


@pytest.mark.unit
@patch("butler.core.context_pipeline.compress_messages")
def test_compress_context_skips_when_not_compacted(mock_compress):
    cfg = LoopConfig(max_context_tokens=128000)
    pipe = ContextPipeline(cfg)
    msgs = [{"role": "user", "content": "x"}]
    mock_compress.return_value = (msgs, "", False)
    pipe.compress_context(msgs)
    assert pipe.compression_summary == ""


@pytest.mark.unit
@patch("butler.hooks.runner.run_post_compact_hooks")
def test_compaction_turn_adapts_hook_context(mock_hooks, monkeypatch):
    from butler.core.compaction_task import run_compaction_turn

    monkeypatch.setenv("BUTLER_COMPACTION_EXPLICIT_TURN", "1")
    monkeypatch.setenv("BUTLER_AUTO_COMPACT", "1")

    msgs = [{"role": "user", "content": f"m{i}"} for i in range(12)]

    def _shrink(m, **kwargs):
        return m[:6]

    mock_hooks.return_value = [
        {"summary": "hook摘要", "tags": ["audit"]},
    ]
    diag: dict = {}
    did, out = run_compaction_turn(
        msgs,
        compress=lambda m, **kw: _shrink(m, **kw),
        diagnostics=diag,
        iteration=1,
        session_key="wechat:test:acl",
    )
    assert did is True
    assert len(out) < len(msgs)
    assert "hook摘要" in str(diag.get("compaction_hook_context") or "")
    assert diag.get("compaction_view_version") == "v1"
