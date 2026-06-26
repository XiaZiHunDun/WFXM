"""Tests for turn_post_inbound_pipeline (ENG-3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from butler.gateway.inbound_pipeline import PipelineResult
from butler.gateway.turn_post_pipeline import run_turn_post_inbound_pipeline


def test_post_pipeline_blocked_reply():
    handler = MagicMock()
    handler._inbound_pipeline = []
    with patch(
        "butler.gateway.inbound_pipeline.run_inbound_pipeline",
        return_value=PipelineResult(text="", blocked=True, block_reply="blocked"),
    ):
        out = run_turn_post_inbound_pipeline(
            handler,
            "hi",
            session_key="sk",
            platform="wechat",
            external_id="cid",
            t0=0.0,
        )
    assert out == "blocked"
    handler._handle_message_locked.assert_not_called()


def test_post_pipeline_sessionless_slash():
    handler = MagicMock()
    handler._inbound_pipeline = []
    handler._handle_message_locked.return_value = "slash-ok"
    with patch(
        "butler.gateway.inbound_pipeline.run_inbound_pipeline",
        return_value=PipelineResult(text="/状态", blocked=False),
    ), patch(
        "butler.gateway.handler_helpers._is_sessionless_command",
        return_value=True,
    ):
        out = run_turn_post_inbound_pipeline(
            handler,
            "/状态",
            session_key="sk",
            platform="wechat",
            external_id="cid",
            t0=0.0,
        )
    assert out == "slash-ok"
    handler._handle_message_locked.assert_called_once()
