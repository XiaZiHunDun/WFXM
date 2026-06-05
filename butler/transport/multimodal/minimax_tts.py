"""MiniMax Text-to-Speech HD client (``speech-2.8-hd``).

Wraps the MiniMax ``/v1/t2a_v2`` endpoint for high-fidelity speech synthesis.

Audit R1-10 [H] layering_violation: this module moved from
``butler.gateway.minimax_tts`` to ``butler.transport.multimodal`` because
it is a pure outbound LLM provider call with no gateway state — it
belongs in the transport layer alongside ``chat_completions`` and
``anthropic_transport``. The old ``butler.gateway.minimax_tts`` path is
kept as a thin re-export shim for back-compat.

Usage::

    from butler.transport.multimodal.minimax_tts import synthesize_speech
    audio_bytes = synthesize_speech("你好，今天天气不错")
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "speech-2.8-hd"
_DEFAULT_VOICE = "male-qn-qingse"
_DEFAULT_FORMAT = "mp3"
_DEFAULT_SAMPLE_RATE = 32000


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


def synthesize_speech(
    text: str,
    *,
    model: str = _DEFAULT_MODEL,
    voice_id: str = _DEFAULT_VOICE,
    audio_format: str = _DEFAULT_FORMAT,
    sample_rate: int = _DEFAULT_SAMPLE_RATE,
    timeout: float = 60.0,
) -> bytes:
    """Synthesize speech from text.

    Returns raw audio bytes in the requested format.

    Raises:
        RuntimeError: if API key is missing or API returns an error.
        ValueError: if text is empty.
    """
    if not text.strip():
        raise ValueError("TTS 文本不能为空")

    key = _api_key()
    if not key:
        raise RuntimeError("MINIMAX_API_KEY 未配置，无法语音合成")

    url = f"{_api_base()}/v1/t2a_v2"
    payload = {
        "model": model,
        "text": text,
        "voice_setting": {
            "voice_id": voice_id,
        },
        "audio_setting": {
            "format": audio_format,
            "sample_rate": sample_rate,
        },
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

    content_type = resp.headers.get("Content-Type", "")

    if "application/json" in content_type:
        data = resp.json()
        base_resp = data.get("base_resp") or {}
        status_code = base_resp.get("status_code", 0)
        if status_code != 0:
            raise RuntimeError(
                f"MiniMax TTS 错误: {status_code}-{base_resp.get('status_msg')}"
            )

        import base64
        audio_b64 = data.get("data", {}).get("audio", "")
        if not audio_b64:
            extra_info = data.get("extra_info") or {}
            audio_b64 = extra_info.get("audio", "")
        if audio_b64:
            audio_bytes = base64.b64decode(audio_b64)
        else:
            raise RuntimeError("MiniMax TTS 返回空音频数据")
    else:
        audio_bytes = resp.content

    if not audio_bytes:
        raise RuntimeError("MiniMax TTS 返回空音频")

    logger.info(
        "TTS synthesized: %d bytes (model=%s, voice=%s, format=%s)",
        len(audio_bytes), model, voice_id, audio_format,
    )
    return audio_bytes


__all__ = ["synthesize_speech"]
