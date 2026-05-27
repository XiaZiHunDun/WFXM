"""Conversational tests — VLM (Vision Language Model) image recognition.

Tests MiniMax Coding Plan VLM integration:
  - Basic photo description
  - OCR text extraction from screenshot
  - Caption-influenced recognition
  - Error handling for invalid images
  - Full inbound media pipeline

Gate: BUTLER_RUN_REAL_API_SMOKE=1 + MINIMAX_API_KEY
Rate limit: MiniMax VLM ~450 calls / 5h, each test uses 1 call.

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_vision.py -v --timeout=60
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).parent / "fixtures"


def _require_vlm():
    if os.getenv("BUTLER_RUN_REAL_API_SMOKE") != "1":
        pytest.skip("set BUTLER_RUN_REAL_API_SMOKE=1 for VLM tests")
    key = (
        os.getenv("MINIMAX_API_KEY", "").strip()
        or os.getenv("MINIMAX_CN_API_KEY", "").strip()
    )
    if not key:
        pytest.skip("set MINIMAX_API_KEY for VLM tests")


@pytest.mark.live_vlm
class TestVLMConversational:
    """MiniMax VLM image understanding tests."""

    def test_vlm_describe_photo(self):
        """Describe a simple shapes image — should return non-empty Chinese."""
        _require_vlm()
        from butler.gateway.minimax_vlm import describe_image

        img = str(_FIXTURES / "test_shapes.png")
        result = describe_image(img, timeout=30.0)
        assert result.strip(), "VLM should return non-empty description"
        assert len(result) > 5, f"Description too short: {result!r}"

    def test_vlm_ocr_screenshot(self):
        """OCR a screenshot with Chinese text — should extract key text."""
        _require_vlm()
        from butler.gateway.minimax_vlm import describe_image

        img = str(_FIXTURES / "test_screenshot.png")
        result = describe_image(img, timeout=30.0)
        assert result.strip(), "VLM should return non-empty OCR result"
        has_relevant = any(
            kw in result for kw in ("会议", "通知", "2026", "会议室", "14")
        )
        assert has_relevant, (
            f"OCR should extract meeting-related text, got: {result!r}"
        )

    def test_vlm_with_caption(self):
        """Caption should influence the VLM output."""
        _require_vlm()
        from butler.gateway.minimax_vlm import describe_image

        img = str(_FIXTURES / "test_note.png")
        result_no_caption = describe_image(img, timeout=30.0)
        result_with_caption = describe_image(
            img, caption="这是一个测试便签图片", timeout=30.0
        )
        assert result_no_caption.strip()
        assert result_with_caption.strip()

    def test_vlm_error_handling(self):
        """Invalid image path should raise FileNotFoundError."""
        _require_vlm()
        from butler.gateway.minimax_vlm import describe_image

        with pytest.raises(FileNotFoundError):
            describe_image("/nonexistent/path/to/image.jpg", timeout=10.0)

    def test_inbound_media_pipeline(self):
        """Full inbound pipeline: build_inbound_user_text with image."""
        _require_vlm()
        from butler.gateway.minimax_vlm import describe_image

        img = str(_FIXTURES / "test_shapes.png")
        description = describe_image(img, caption="看看这个图片", timeout=30.0)
        assert description.strip(), "Pipeline should produce a description"
        assert len(description) >= 5
