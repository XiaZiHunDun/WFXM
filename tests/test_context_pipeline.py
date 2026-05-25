"""Unit tests for butler.core.context_pipeline."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.core.context_pipeline import ContextPipeline
from butler.core.loop_types import LoopConfig


@pytest.mark.unit
def test_compress_context_short_messages_unchanged():
    pipeline = ContextPipeline(LoopConfig(max_context_tokens=100000))
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    assert pipeline.compress_context(msgs) == msgs


@pytest.mark.unit
def test_compress_context_long_drops_middle():
    pipeline = ContextPipeline(LoopConfig(max_context_tokens=5))
    msgs = [{"role": "system", "content": "system prompt"}]
    for _ in range(20):
        msgs.append({"role": "user", "content": "x" * 200})
    compressed = pipeline.compress_context(msgs)
    assert any(m.get("role") == "system" for m in compressed)
    from butler.core.context_compressor import SUMMARY_PREFIX

    assert len(compressed) < len(msgs) or any(
        SUMMARY_PREFIX[:20] in str(m.get("content", "")) for m in compressed
    )


@pytest.mark.unit
def test_prepare_messages_for_api_runs_repair_and_sanitize():
    pipeline = ContextPipeline(LoopConfig(max_context_tokens=100000))
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    prepared = pipeline.prepare_messages_for_api(msgs)
    assert prepared[0]["role"] == "system"
    assert prepared[-1]["content"] == "hi"


@pytest.mark.unit
def test_hygiene_compress_skips_below_threshold():
    pipeline = ContextPipeline(LoopConfig(max_context_tokens=1000))
    messages = [{"role": "user", "content": "short"} for _ in range(20)]
    diagnostics: dict = {}

    with patch.object(pipeline, "compress_context", wraps=pipeline.compress_context) as compress:
        compressed, updated = pipeline.hygiene_compress_if_needed(messages, diagnostics)

    assert compressed is False
    assert updated == messages
    compress.assert_not_called()


@pytest.mark.unit
def test_hygiene_compress_when_over_auto_threshold():
    pipeline = ContextPipeline(LoopConfig(max_context_tokens=128_000))
    messages = [{"role": "user", "content": "x" * 100} for _ in range(20)]
    compressed_msgs = [{"role": "user", "content": "summary"}]
    diagnostics: dict = {}

    with patch.object(pipeline, "compress_context", return_value=compressed_msgs) as compress:
        with patch.object(pipeline, "estimate_tokens", return_value=100_000):
            with patch(
                "butler.core.context_pipeline.run_post_compact_cleanup",
                return_value=compressed_msgs,
            ):
                compressed, updated = pipeline.hygiene_compress_if_needed(
                    messages, diagnostics
                )

    assert compressed is True
    assert updated == compressed_msgs
    compress.assert_called_once()
    assert compress.call_args.kwargs["threshold_ratio"] == 0.0
    assert diagnostics["hygiene_compressed"] is True


@pytest.mark.unit
def test_compress_context_applies_post_compact_anchor(monkeypatch):
    pipeline = ContextPipeline(LoopConfig(max_context_tokens=5))
    msgs = [{"role": "system", "content": "system prompt"}]
    for _ in range(20):
        msgs.append({"role": "user", "content": "x" * 200})

    with patch(
        "butler.core.context_compressor.auxiliary_complete",
        return_value="## Active Task\n- keep going",
    ):
        with patch(
            "butler.core.post_compact_cleanup.build_post_compact_anchor_text",
            return_value="[POST-COMPACT ANCHORS — REFERENCE ONLY]\n## Memory anchor\nfoo",
        ):
            compressed = pipeline.compress_context(msgs)

    from butler.core.context_compressor import SUMMARY_PREFIX
    from butler.core.post_compact_cleanup import POST_COMPACT_PREFIX

    assert any(SUMMARY_PREFIX[:20] in str(m.get("content", "")) for m in compressed)
    assert any(POST_COMPACT_PREFIX[:20] in str(m.get("content", "")) for m in compressed)
