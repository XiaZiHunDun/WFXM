"""Vision fallbacks when MiniMax VLM fails (OpenAI-compatible, optional local OCR)."""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

import requests

from butler.defaults.model_defaults import OPENAI_VISION_DEFAULT_MODEL

logger = logging.getLogger(__name__)


def _fallback_order() -> list[str]:
    raw = os.getenv("BUTLER_WECHAT_VISION_FALLBACK", "openai,ocr").strip().lower()
    if not raw or raw in ("0", "off", "none"):
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def describe_image_openai(path: Path, *, caption: str = "", timeout: float = 45.0) -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY 未配置")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv(
        "OPENAI_VISION_MODEL",
        os.getenv("OPENAI_MODEL", OPENAI_VISION_DEFAULT_MODEL),
    ).strip()
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    suffix = path.suffix.lower()
    mime = "image/jpeg"
    if suffix == ".png":
        mime = "image/png"
    elif suffix == ".webp":
        mime = "image/webp"
    prompt = (
        "用中文简要说明图片内容；若是截图或文档优先提取可见文字。"
        f"用户说明：{(caption or '').strip() or '（无）'}"
    )
    url = f"{base_url}/chat/completions"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                    ],
                }
            ],
            "max_tokens": 500,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenAI Vision 返回空 choices")
    content = (choices[0].get("message") or {}).get("content") or ""
    text = content.strip() if isinstance(content, str) else str(content).strip()
    if not text:
        raise RuntimeError("OpenAI Vision 返回空内容")
    return text


def describe_image_ocr(path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("本地 OCR 需要 pip install pytesseract pillow") from exc
    img = Image.open(path)
    text = pytesseract.image_to_string(img, lang="chi_sim+eng")
    text = (text or "").strip()
    if not text:
        raise RuntimeError("OCR 未识别到文字")
    return text[:800]


def describe_image_with_fallbacks(
    path: str,
    *,
    caption: str = "",
    primary_error: Exception | None = None,
    timeout: float | None = None,
) -> tuple[str, str]:
    """
    Try configured fallback providers after primary MiniMax failure.

    Returns (description, provider_name).
    """
    to = timeout if timeout is not None else 45.0
    p = Path(path).expanduser().resolve()
    errors: list[str] = []
    if primary_error is not None:
        errors.append(f"minimax: {primary_error}")

    for name in _fallback_order():
        try:
            if name == "openai":
                return describe_image_openai(p, caption=caption, timeout=to), "openai"
            if name in ("ocr", "tesseract", "local"):
                return describe_image_ocr(p), "ocr"
        except Exception as exc:
            logger.warning("Vision fallback %s failed: %s", name, exc)
            errors.append(f"{name}: {exc}")

    hint = "; ".join(errors) if errors else "无可用 fallback"
    raise RuntimeError(hint)
