"""MiniMax Coding Plan VLM (image understanding) for WeChat inbound media."""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import cast

import requests

_VISION_PROMPT = (
    "你是微信助手的前置视觉模块。请用中文简要说明图片内容；"
    "若像截图或文档则优先提取可见文字（OCR）。控制在 200 字以内。"
    "用户附带说明：{caption}"
)


def _api_host() -> str:
    """Align with main Butler LLM (``MINIMAX_BASE_URL``), not a separate global host."""
    from butler.gateway_settings import vision_api_host

    return cast(str, vision_api_host())


def _api_key() -> str:
    return (
        os.getenv("MINIMAX_API_KEY", "").strip()
        or os.getenv("MINIMAX_CN_API_KEY", "").strip()
    )


def _image_to_data_url(path: Path) -> str:
    p = path.expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    data = p.read_bytes()
    fmt = "jpeg"
    low = p.suffix.lower()
    if low == ".png":
        fmt = "png"
    elif low == ".webp":
        fmt = "webp"
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/{fmt};base64,{b64}"


def _describe_minimax(path: str, *, caption: str = "", timeout: float) -> str:
    key = _api_key()
    if not key:
        raise RuntimeError("MINIMAX_API_KEY 未配置，无法识图")
    prompt = _VISION_PROMPT.format(caption=(caption or "").strip() or "（无）")
    payload = {
        "prompt": prompt,
        "image_url": _image_to_data_url(Path(path)),
    }
    from butler.gateway_settings import vision_endpoint_path

    url = f"{_api_host()}/v1/{vision_endpoint_path()}"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "MM-API-Source": "Butler-WeChat-Gateway",
        },
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    base_resp = data.get("base_resp") or {}
    if base_resp.get("status_code") not in (0, None):
        raise RuntimeError(
            f"MiniMax VLM 错误: {base_resp.get('status_code')}-{base_resp.get('status_msg')}"
        )
    content = (data.get("content") or "").strip()
    if not content:
        raise RuntimeError("MiniMax VLM 返回空内容")
    return content


def describe_image(path: str, *, caption: str = "", timeout: float | None = None) -> str:
    """MiniMax VLM, then optional OpenAI/OCR fallbacks. Records telemetry."""
    from butler.gateway.media_telemetry import record_media_event
    from butler.defaults.model_defaults import GATEWAY_VISION_PROVIDER
    from butler.gateway_settings import resolve_gateway_inbound_config

    to = timeout if timeout is not None else resolve_gateway_inbound_config().vision.timeout_seconds
    t0 = time.monotonic()
    from butler.gateway.minimax_vlm_ops import (
        describe_minimax_primary_safe,
        describe_with_fallbacks_safe,
    )

    text, primary_exc = describe_minimax_primary_safe(
        lambda: _describe_minimax(path, caption=caption, timeout=to),
        path=path,
    )
    if text is not None:
        record_media_event(
            "vision",
            provider=GATEWAY_VISION_PROVIDER,
            ok=True,
            duration_ms=(time.monotonic() - t0) * 1000,
        )
        return cast(str, text)

    from butler.gateway.vision_fallback import describe_image_with_fallbacks

    fallback_text, provider, fallback_exc = describe_with_fallbacks_safe(
        lambda: describe_image_with_fallbacks(
            path,
            caption=caption,
            primary_error=primary_exc,
            timeout=to,
        )
    )
    if fallback_text is not None and provider is not None:
        record_media_event(
            "vision",
            provider=provider,
            ok=True,
            duration_ms=(time.monotonic() - t0) * 1000,
            detail="fallback",
        )
        return cast(str, fallback_text)

    record_media_event(
        "vision",
        provider="minimax+fallback",
        ok=False,
        duration_ms=(time.monotonic() - t0) * 1000,
        detail=str(fallback_exc or primary_exc or "vision failed")[:80],
    )
    if fallback_exc is not None:
        raise fallback_exc
    if primary_exc is not None:
        raise primary_exc
    raise RuntimeError("vision failed")
