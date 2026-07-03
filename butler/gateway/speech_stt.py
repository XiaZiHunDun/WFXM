"""Inbound voice STT — iLink text preferred; local fallback for .silk (MiniMax has no public ASR)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def stt_provider() -> str:
    from butler.gateway_settings import resolve_gateway_inbound_config

    return resolve_gateway_inbound_config().speech.stt_provider


def silk_to_wav(silk_path: Path, wav_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，无法转写微信语音")
    proc = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(silk_path),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(wav_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[-400:]
        raise RuntimeError(f"ffmpeg 转码失败: {err}")


def transcribe_wav_local(wav_path: Path) -> str:
    """Optional faster-whisper (``pip install faster-whisper``)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "未安装 faster-whisper，无法转写纯语音文件（pip install faster-whisper）"
        ) from exc

    from butler.gateway_settings import resolve_gateway_inbound_config

    model_size = resolve_gateway_inbound_config().speech.whisper_model
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(wav_path), language="zh")
    parts = [seg.text.strip() for seg in segments if seg.text.strip()]
    text = "".join(parts).strip()
    if not text:
        raise RuntimeError("语音转写结果为空")
    return text


def transcribe_voice_file(path: str) -> str:
    """Transcribe cached WeChat voice (.silk or .wav)."""
    import time

    t0 = time.monotonic()
    provider = stt_provider()
    if provider in ("off", "none", "0"):
        raise RuntimeError("语音转写已关闭（BUTLER_WECHAT_STT_PROVIDER=off）")

    src = Path(path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(str(src))

    from butler.gateway.speech_stt_ops import transcribe_with_stt_telemetry

    def _run() -> str:
        with tempfile.TemporaryDirectory(prefix="butler-stt-") as tmp:
            wav = Path(tmp) / "voice.wav"
            if src.suffix.lower() == ".wav":
                wav = src
            else:
                silk_to_wav(src, wav)
            if provider == "local":
                return transcribe_wav_local(wav)
            raise RuntimeError(f"未知 STT provider: {provider}")

    return transcribe_with_stt_telemetry(_run, provider=provider, t0=t0)
