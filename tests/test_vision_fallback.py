"""Tests for butler.gateway.vision_fallback."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from butler.gateway import vision_fallback as vf


class TestFallbackOrder:
    def test_default_openai_ocr(self, monkeypatch):
        monkeypatch.delenv("BUTLER_WECHAT_VISION_FALLBACK", raising=False)
        assert vf._fallback_order() == ["openai", "ocr"]

    @pytest.mark.parametrize("value", ["", "0", "off", "none"])
    def test_disabled_values_return_empty(self, monkeypatch, value):
        monkeypatch.setenv("BUTLER_WECHAT_VISION_FALLBACK", value)
        assert vf._fallback_order() == []

    def test_custom_value_splits(self, monkeypatch):
        monkeypatch.setenv("BUTLER_WECHAT_VISION_FALLBACK", " openai , tesseract , ")
        assert vf._fallback_order() == ["openai", "tesseract"]


class TestDescribeImageOpenai:
    def test_missing_api_key_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")

        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            vf.describe_image_openai(img)

    @patch("butler.gateway.vision_fallback.requests.post")
    def test_empty_choices_raises(self, mock_post, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")

        mock_resp = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        mock_resp.json.return_value = {"choices": []}
        mock_resp.raise_for_status = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="空 choices"):
            vf.describe_image_openai(img)

    @patch("butler.gateway.vision_fallback.requests.post")
    def test_extracts_content(self, mock_post, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff")

        mock_resp = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "  一张图片  "}}]
        }
        mock_resp.raise_for_status = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        mock_post.return_value = mock_resp

        assert vf.describe_image_openai(img) == "一张图片"


class TestDescribeImageWithFallbacks:
    @patch("butler.gateway.vision_fallback.describe_image_openai")
    def test_all_fallbacks_fail_includes_all_errors(
        self, mock_openai, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("BUTLER_WECHAT_VISION_FALLBACK", "openai")
        img = tmp_path / "pic.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        mock_openai.side_effect = RuntimeError("api down")
        primary = RuntimeError("minimax timeout")

        with pytest.raises(RuntimeError) as exc_info:
            vf.describe_image_with_fallbacks(
                str(img), primary_error=primary
            )

        msg = str(exc_info.value)
        assert "minimax: minimax timeout" in msg
        assert "openai: api down" in msg

    @patch("butler.gateway.vision_fallback.describe_image_openai")
    def test_primary_error_recorded_when_no_fallbacks(
        self, mock_openai, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("BUTLER_WECHAT_VISION_FALLBACK", "none")
        img = tmp_path / "pic.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        primary = ValueError("vlm failed")

        with pytest.raises(RuntimeError, match="minimax: vlm failed"):
            vf.describe_image_with_fallbacks(str(img), primary_error=primary)

        mock_openai.assert_not_called()
