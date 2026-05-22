"""Tests for WeChat inbound media → user text."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.gateway.inbound_media import build_inbound_user_text, inbound_media_enabled
from butler.gateway.platforms.types import MessageEvent, MessageType, SessionSource


def _event(**kwargs) -> MessageEvent:
    defaults = {
        "text": "",
        "message_type": MessageType.TEXT,
        "source": SessionSource(platform="wechat", chat_id="u1"),
        "media_urls": [],
        "media_types": [],
    }
    defaults.update(kwargs)
    return MessageEvent(**defaults)


class TestInboundMediaEnabled:
    def test_default_on(self, monkeypatch):
        monkeypatch.delenv("BUTLER_WECHAT_INBOUND_MEDIA", raising=False)
        assert inbound_media_enabled()

    def test_off(self, monkeypatch):
        monkeypatch.setenv("BUTLER_WECHAT_INBOUND_MEDIA", "0")
        assert not inbound_media_enabled()


class TestBuildInboundUserText:
    def test_plain_text_unchanged(self):
        ev = _event(text="你好")
        assert build_inbound_user_text(ev) == "你好"

    def test_media_disabled_placeholder(self, monkeypatch):
        monkeypatch.setenv("BUTLER_WECHAT_INBOUND_MEDIA", "0")
        ev = _event(media_urls=["/tmp/a.jpg"], media_types=["image/jpeg"])
        out = build_inbound_user_text(ev)
        assert "收到媒体消息" in out

    def test_image_with_vision(self, monkeypatch, tmp_path):
        img = tmp_path / "x.jpg"
        img.write_bytes(b"\xff\xd8\xff")
        ev = _event(
            text="看图",
            media_urls=[str(img)],
            media_types=["image/jpeg"],
            message_type=MessageType.PHOTO,
        )
        with patch(
            "butler.gateway.minimax_vlm.describe_image",
            return_value="屏幕上有报错",
        ):
            out = build_inbound_user_text(ev)
        assert "[微信图片]" in out
        assert "看图" in out
        assert "屏幕上有报错" in out

    def test_image_vision_failure_degrades(self, monkeypatch, tmp_path):
        img = tmp_path / "x.jpg"
        img.write_bytes(b"\xff\xd8\xff")
        ev = _event(media_urls=[str(img)], media_types=["image/jpeg"])
        with patch(
            "butler.gateway.minimax_vlm.describe_image",
            side_effect=RuntimeError("timeout"),
        ):
            out = build_inbound_user_text(ev)
        assert "识别失败" in out

    def test_voice_ilink_text_prefix(self):
        ev = _event(
            text="明天开会",
            message_type=MessageType.VOICE,
        )
        out = build_inbound_user_text(ev)
        assert out.startswith("[微信语音转写]")
        assert "明天开会" in out

    def test_voice_prefer_ilink_skips_stt(self, monkeypatch, tmp_path):
        silk = tmp_path / "v.silk"
        silk.write_bytes(b"\x00")
        ev = _event(
            text="iLink 转写内容",
            media_urls=[str(silk)],
            media_types=["audio/silk"],
            message_type=MessageType.VOICE,
        )
        with patch(
            "butler.gateway.speech_stt.transcribe_voice_file",
            side_effect=AssertionError("STT should not run"),
        ):
            out = build_inbound_user_text(ev)
        assert "iLink 转写内容" in out
        assert "[微信语音转写]" in out

    def test_voice_prefer_ilink_off_uses_stt(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BUTLER_WECHAT_PREFER_ILINK_TEXT", "0")
        silk = tmp_path / "v.silk"
        silk.write_bytes(b"\x00")
        ev = _event(
            text="应忽略",
            media_urls=[str(silk)],
            media_types=["audio/silk"],
            message_type=MessageType.VOICE,
        )
        with patch(
            "butler.gateway.speech_stt.transcribe_voice_file",
            return_value="本地转写",
        ):
            out = build_inbound_user_text(ev)
        assert "本地转写" in out
        assert "应忽略" not in out

    def test_voice_file_stt(self, monkeypatch, tmp_path):
        silk = tmp_path / "v.silk"
        silk.write_bytes(b"\x00")
        ev = _event(
            media_urls=[str(silk)],
            media_types=["audio/silk"],
            message_type=MessageType.VOICE,
        )
        with patch(
            "butler.gateway.speech_stt.transcribe_voice_file",
            return_value="请帮忙查一下",
        ):
            out = build_inbound_user_text(ev)
        assert "[微信语音转写]" in out
        assert "请帮忙查一下" in out
