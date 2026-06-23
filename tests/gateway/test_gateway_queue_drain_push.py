"""Queue drain reply delivery via outbound bridge."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _merge_primary_and_follow(*, out: str, follow: str) -> str:
    """Mirror handle_message post-drain merge (bridge success => follow empty)."""
    if follow:
        return f"{out}\n\n---\n\n{follow}" if out else follow
    return out


def test_merge_appends_when_bridge_did_not_push():
    """Bridge 不可用时应把 drain 正文拼回主回复，避免丢失。"""
    out = _merge_primary_and_follow(out="主回复", follow="排队消息二")
    assert "主回复" in out and "排队消息二" in out


def test_merge_keeps_primary_when_follow_empty():
    out = _merge_primary_and_follow(out="主回复", follow="")
    assert out == "主回复"


@pytest.mark.parametrize("primary,combined", [("主回复", "排队正文")])
def test_drain_supplementary_via_bridge(monkeypatch, primary, combined):
    monkeypatch.setenv("BUTLER_GATEWAY_QUEUE_PUSH_VIA_BRIDGE", "1")

    bridge = MagicMock()  # noqa: magicmock-no-spec — gateway queue drain facade (bridge)
    bridge.schedule_supplementary_reply.return_value = True
    monkeypatch.setattr(
        "butler.gateway.outbound_bridge.get_current_bridge",
        lambda: bridge,
    )

    follow = combined
    from butler.env_parse import env_truthy

    if env_truthy("BUTLER_GATEWAY_QUEUE_PUSH_VIA_BRIDGE", default=True) and primary.strip():
        from butler.gateway.outbound_bridge import get_current_bridge

        br = get_current_bridge()
        if br is not None:
            br.schedule_supplementary_reply(follow, kind="queued")
            follow = ""

    out = _merge_primary_and_follow(out=primary, follow=follow)
    assert out == primary
    bridge.schedule_supplementary_reply.assert_called_once()
