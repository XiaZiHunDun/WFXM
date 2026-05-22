"""MiniMax Coding Plan VLM (image understanding) for WeChat inbound media."""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_VISION_PROMPT = (
    "你是微信助手的前置视觉模块。请用中文简要说明图片内容；"
    "若像截图或文档则优先提取可见文字（OCR）。控制在 200 字以内。"
    "用户附带说明：{caption}"
)


def _api_host() -> str:
    """Align with main Butler LLM (``MINIMAX_BASE_URL``), not a separate global host."""
    from butler.gateway_settings import vision_api_host

    return vision_api_host()


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


def describe_image(path: str, *, caption: str = "", timeout: float | None = None) -> str:
    """Call MiniMax ``/v1/coding_plan/vlm``. Returns description or raises."""
    key = _api_key()
    if not key:
        raise RuntimeError("MINIMAX_API_KEY 未配置，无法识图")

    from butler.gateway_settings import resolve_gateway_inbound_config

    to = timeout if timeout is not None else resolve_gateway_inbound_config().vision.timeout_seconds
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
        timeout=to,
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
