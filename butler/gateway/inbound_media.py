"""Build user-visible text from WeChat inbound media (image + voice)."""

from __future__ import annotations

import logging
import os

from butler.gateway.platforms.types import MessageEvent, MessageType

logger = logging.getLogger(__name__)

_PLACEHOLDER = "（收到媒体消息；当前 Butler 网关会处理文字指令，请用文字说明需求。）"


def inbound_media_enabled() -> bool:
    from butler.gateway_settings import resolve_gateway_inbound_config

    return resolve_gateway_inbound_config().enabled


def _max_chars() -> int:
    from butler.gateway_settings import resolve_gateway_inbound_config

    return resolve_gateway_inbound_config().max_chars


def _truncate(text: str) -> str:
    limit = _max_chars()
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 3] + "..."


def _pair_media(event: MessageEvent) -> tuple[list[str], list[str]]:
    images: list[str] = []
    voices: list[str] = []
    for url, mime in zip(event.media_urls or [], event.media_types or []):
        m = (mime or "").lower()
        if m.startswith("image/"):
            images.append(url)
        elif m.startswith("audio/") or "silk" in m:
            voices.append(url)
    return images, voices


def build_inbound_user_text(event: MessageEvent) -> str:
    """Turn MessageEvent into orchestrator user message text."""
    base = (event.text or "").strip()
    if not inbound_media_enabled():
        if base:
            return base
        if event.media_urls:
            return _PLACEHOLDER
        return ""

    images, voices = _pair_media(event)
    blocks: list[str] = []

    if images:
        from butler.gateway.minimax_vlm import describe_image

        if base:
            blocks.append(f"[微信图片]\n（用户附图说明：{base}）")
        else:
            blocks.append("[微信图片]")
        for img_path in images[:3]:
            try:
                hint = base if len(images) == 1 else ""
                summary = describe_image(img_path, caption=hint)
                logger.info(
                    "WeChat vision ok path=%s chars=%d",
                    img_path,
                    len(summary),
                )
                blocks.append(f"--- 图片识别 ---\n{summary}")
            except Exception as exc:
                logger.warning("WeChat vision failed for %s: %s", img_path, exc)
                blocks.append(f"--- 图片识别 ---\n（识别失败：{exc}）")
        base = ""

    if voices:
        from butler.gateway.speech_stt import transcribe_voice_file
        from butler.gateway_settings import resolve_gateway_inbound_config

        prefer_ilink = resolve_gateway_inbound_config().speech.prefer_ilink_text
        ilink_text = base.strip() if base else ""

        if prefer_ilink and ilink_text:
            blocks.append(f"[微信语音转写]\n{ilink_text}")
            base = ""
        else:
            for vpath in voices[:2]:
                try:
                    text = transcribe_voice_file(vpath)
                    blocks.append(f"[微信语音转写]\n{text}")
                    base = ""
                except Exception as exc:
                    logger.warning("WeChat STT failed for %s: %s", vpath, exc)
                    if ilink_text:
                        blocks.append(f"[微信语音转写]\n{ilink_text}")
                        base = ""
                    else:
                        blocks.append(
                            "--- 语音转写 ---\n"
                            f"（转写失败：{exc}。请用文字重说，或安装 ffmpeg + faster-whisper）"
                        )
            base = ""

    if base:
        if event.message_type == MessageType.VOICE and not voices:
            blocks.append(f"[微信语音转写]\n{base}")
        else:
            blocks.append(base)

    if not blocks:
        return _PLACEHOLDER if event.media_urls else ""

    return _truncate("\n\n".join(blocks))
