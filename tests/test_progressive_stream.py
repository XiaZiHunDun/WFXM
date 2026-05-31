"""Tests for butler.gateway.progressive_stream."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from butler.gateway import progressive_stream as ps


class TestProgressiveStreamEnabled:
    def test_default_false(self, monkeypatch):
        monkeypatch.delenv("BUTLER_GATEWAY_PROGRESSIVE_STREAM", raising=False)
        assert ps.progressive_stream_enabled() is False

    def test_env_one_returns_true(self, monkeypatch):
        monkeypatch.setenv("BUTLER_GATEWAY_PROGRESSIVE_STREAM", "1")
        assert ps.progressive_stream_enabled() is True


class TestFormatProgressiveChunk:
    def test_empty_content_returns_empty_string(self):
        assert ps.format_progressive_chunk("") == ""
        assert ps.format_progressive_chunk("   ") == ""

    def test_normal_content_format(self):
        assert ps.format_progressive_chunk("hello") == "⏳ 处理中…\nhello"

    def test_long_content_truncated_to_320_chars(self):
        body = "x" * 400
        result = ps.format_progressive_chunk(body)
        assert result.startswith("⏳ 处理中…\n")
        assert len(result) == len("⏳ 处理中…\n") + 320
        assert result.endswith("...")


class TestMaybeScheduleProgressiveReply:
    def test_bridge_none_does_nothing(self, monkeypatch):
        monkeypatch.setenv("BUTLER_GATEWAY_PROGRESSIVE_STREAM", "1")
        ps.maybe_schedule_progressive_reply(None, "preview text")

    def test_disabled_does_nothing(self, monkeypatch):
        monkeypatch.delenv("BUTLER_GATEWAY_PROGRESSIVE_STREAM", raising=False)
        bridge = MagicMock()
        ps.maybe_schedule_progressive_reply(bridge, "preview text")
        bridge.schedule_supplementary_reply.assert_not_called()

    def test_enabled_calls_schedule_supplementary_reply(self, monkeypatch):
        monkeypatch.setenv("BUTLER_GATEWAY_PROGRESSIVE_STREAM", "1")
        monkeypatch.setenv("BUTLER_GATEWAY_PROGRESSIVE_MIN_CHARS", "80")
        monkeypatch.setenv("BUTLER_GATEWAY_PROGRESSIVE_INTERVAL", "15")

        bridge = MagicMock()
        bridge._progressive_last_at = 0.0
        bridge._stream_chars = 100
        bridge.schedule_supplementary_reply.return_value = True

        ps.maybe_schedule_progressive_reply(bridge, "streaming preview")

        bridge.schedule_supplementary_reply.assert_called_once_with(
            "⏳ 处理中…\nstreaming preview",
            kind="progressive_stream",
        )
