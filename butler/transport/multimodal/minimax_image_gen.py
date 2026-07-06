"""MiniMax Image Generation client (``image-01``).

Wraps the MiniMax ``/v1/image_generation`` endpoint for text-to-image.

Audit R1-10 [H] layering_violation: this module moved from
``butler.gateway.minimax_image_gen`` to ``butler.transport.multimodal``
because it is a pure outbound LLM provider call with no gateway state —
it belongs in the transport layer alongside ``chat_completions`` and
``anthropic_transport``. The old ``butler.gateway.minimax_image_gen``
path is kept as a thin re-export shim for back-compat.

Usage::

    from butler.transport.multimodal.minimax_image_gen import generate_image
    url = generate_image("一只可爱的猫咪在窗台上晒太阳")
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "image-01"
_DEFAULT_ASPECT = "1:1"
_VALID_ASPECTS = {"1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"}


def _api_key() -> str:
    return (
        os.getenv("MINIMAX_API_KEY", "").strip()
        or os.getenv("MINIMAX_CN_API_KEY", "").strip()
    )


def _api_base() -> str:
    return (
        os.getenv("MINIMAX_BASE_URL", "").strip()
        or "https://api.minimax.chat"
    )


def generate_image(
    prompt: str,
    *,
    model: str = _DEFAULT_MODEL,
    aspect_ratio: str = _DEFAULT_ASPECT,
    timeout: float = 60.0,
) -> str:
    """Generate an image from a text prompt.

    Returns the URL of the generated image.

    Raises:
        RuntimeError: if API key is missing or API returns an error.
    """
    key = _api_key()
    if not key:
        raise RuntimeError("MINIMAX_API_KEY 未配置，无法生成图片")

    if aspect_ratio not in _VALID_ASPECTS:
        logger.warning(
            "aspect_ratio %r not in %s, using %s",
            aspect_ratio, _VALID_ASPECTS, _DEFAULT_ASPECT,
        )
        aspect_ratio = _DEFAULT_ASPECT

    url = f"{_api_base()}/v1/image_generation"
    payload = {
        "model": model,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
    }

    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()

    data = resp.json()
    base_resp = data.get("base_resp") or {}
    status_code = base_resp.get("status_code", 0)
    if status_code != 0:
        raise RuntimeError(
            f"MiniMax 图像生成错误: {status_code}-{base_resp.get('status_msg')}"
        )

    image_data = data.get("data") or {}
    image_url = image_data.get("image_url", "")
    if not image_url:
        raise RuntimeError("MiniMax 图像生成返回空 URL")

    logger.info("Image generated: %s (model=%s, aspect=%s)", image_url[:80], model, aspect_ratio)
    return str(image_url)


__all__ = ["generate_image"]
