"""Conversational tests — MiniMax multimodal capabilities.

Tests image generation and TTS (Text-to-Speech) integration:
  - Image generation (3 cases)
  - TTS speech synthesis (3 cases)

Gate: BUTLER_RUN_REAL_API_SMOKE=1 + MINIMAX_API_KEY

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_multimodal.py -v --timeout=120
"""

from __future__ import annotations

import os

import pytest


def _require_minimax_key():
    if os.getenv("BUTLER_RUN_REAL_API_SMOKE") != "1":
        pytest.skip("set BUTLER_RUN_REAL_API_SMOKE=1 for multimodal tests")
    key = (
        os.getenv("MINIMAX_API_KEY", "").strip()
        or os.getenv("MINIMAX_CN_API_KEY", "").strip()
    )
    if not key:
        pytest.skip("set MINIMAX_API_KEY for multimodal tests")


# =========================================================================
# Image Generation (3)
# =========================================================================


@pytest.mark.live_multimodal
class TestImageGeneration:
    """MiniMax image generation (image-01)."""

    def test_generate_simple_image(self):
        """Generate a simple image — should return a valid URL."""
        _require_minimax_key()
        from butler.gateway.minimax_image_gen import generate_image

        url = generate_image("一只可爱的橘猫在阳光下打盹", timeout=60.0)
        assert url.startswith("http"), f"Expected HTTP URL, got: {url!r}"

    def test_generate_with_aspect_ratio(self):
        """Generate image with 16:9 aspect ratio."""
        _require_minimax_key()
        from butler.gateway.minimax_image_gen import generate_image

        url = generate_image(
            "日落时分的海边风景画",
            aspect_ratio="16:9",
            timeout=60.0,
        )
        assert url.startswith("http"), f"Expected HTTP URL, got: {url!r}"

    def test_generate_error_no_key(self, monkeypatch):
        """Should raise RuntimeError when API key is missing."""
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_CN_API_KEY", raising=False)
        from butler.gateway.minimax_image_gen import generate_image

        with pytest.raises(RuntimeError, match="未配置"):
            generate_image("test prompt")


# =========================================================================
# TTS Speech Synthesis (3)
# =========================================================================


@pytest.mark.live_multimodal
class TestTTSSynthesis:
    """MiniMax TTS (speech-2.8-hd)."""

    def test_synthesize_chinese(self):
        """Synthesize Chinese text — should return non-empty audio bytes."""
        _require_minimax_key()
        from butler.gateway.minimax_tts import synthesize_speech

        audio = synthesize_speech("你好，今天天气真不错", timeout=30.0)
        assert isinstance(audio, bytes)
        assert len(audio) > 100, f"Audio too small: {len(audio)} bytes"

    def test_synthesize_empty_text(self):
        """Empty text should raise ValueError."""
        from butler.gateway.minimax_tts import synthesize_speech

        with pytest.raises(ValueError, match="不能为空"):
            synthesize_speech("")

    def test_synthesize_no_key(self, monkeypatch):
        """Should raise RuntimeError when API key is missing."""
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_CN_API_KEY", raising=False)
        from butler.gateway.minimax_tts import synthesize_speech

        with pytest.raises(RuntimeError, match="未配置"):
            synthesize_speech("测试文本")
