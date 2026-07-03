"""Multimodal tool fail-closed helpers (P0-A)."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def run_multimodal_tool_safe(
    run: Callable[[], dict],
    *,
    label: str,
) -> str:
    try:
        payload = run()
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        logger.warning("%s failed: %s", label, exc)
        return json.dumps({"error": str(exc)})


def write_tts_output_safe(output_dir: Path, audio_bytes: bytes, *, voice_id: str, text_length: int) -> dict:
    filename = f"tts_{uuid.uuid4().hex[:8]}.mp3"
    out_path = output_dir / filename
    out_path.write_bytes(audio_bytes)
    return {
        "ok": True,
        "file": str(out_path),
        "size_bytes": len(audio_bytes),
        "voice_id": voice_id,
        "text_length": text_length,
    }
