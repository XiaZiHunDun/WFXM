"""Multimodal output tools — image generation and speech synthesis via MiniMax."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, cast

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)


def _image_gen_enabled() -> bool:
    return bool(env_truthy("BUTLER_IMAGE_GENERATION", default=True))


def _tts_enabled() -> bool:
    return bool(env_truthy("BUTLER_TTS", default=True))


def _output_dir() -> Path:
    from butler.config import get_butler_home
    d = Path(get_butler_home() / "media_output")
    d.mkdir(parents=True, exist_ok=True)
    return d


def tool_generate_image(prompt: str = "", aspect_ratio: str = "1:1", **_: Any) -> str:
    """Generate an image from a text description using MiniMax image-01."""
    if not _image_gen_enabled():
        return json.dumps({"error": "image generation disabled", "hint": "set BUTLER_IMAGE_GENERATION=1"})

    prompt = (prompt or "").strip()
    if not prompt:
        return json.dumps({"error": "prompt is required"})

    from butler.tools.multimodal_tools_ops import run_multimodal_tool_safe, write_tts_output_safe

    def _run() -> dict[str, Any]:
        from butler.transport.multimodal.minimax_image_gen import generate_image

        image_url = generate_image(prompt, aspect_ratio=aspect_ratio)
        return {
            "ok": True,
            "image_url": image_url,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
        }

    return str(run_multimodal_tool_safe(_run, label="generate_image"))


def tool_synthesize_speech(text: str = "", voice_id: str = "male-qn-qingse", **_: Any) -> str:
    """Synthesize speech from text using MiniMax TTS HD."""
    if not _tts_enabled():
        return json.dumps({"error": "TTS disabled", "hint": "set BUTLER_TTS=1"})

    text = (text or "").strip()
    if not text:
        return json.dumps({"error": "text is required"})
    if len(text) > 5000:
        return json.dumps({"error": "text too long (max 5000 chars)"})

    from butler.tools.multimodal_tools_ops import run_multimodal_tool_safe, write_tts_output_safe

    def _run() -> dict[str, Any]:
        from butler.transport.multimodal.minimax_tts import synthesize_speech

        audio_bytes = synthesize_speech(text, voice_id=voice_id)
        return cast(
            dict[str, Any],
            write_tts_output_safe(
                _output_dir(),
                audio_bytes,
                voice_id=voice_id,
                text_length=len(text),
            ),
        )

    return str(run_multimodal_tool_safe(_run, label="synthesize_speech"))


def register_multimodal_tools(register_fn: Callable[..., None]) -> None:
    """Register image generation and TTS tools."""
    register_fn(
        name="generate_image",
        description=(
            "Generate an image from a text description using AI (MiniMax image-01). "
            "Returns the URL of the generated image. Supports aspect ratios: "
            "1:1, 16:9, 9:16, 4:3, 3:4."
        ),
        schema={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Image description / prompt text",
                },
                "aspect_ratio": {
                    "type": "string",
                    "default": "1:1",
                    "enum": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"],
                    "description": "Image aspect ratio",
                },
            },
            "required": ["prompt"],
        },
        handler=tool_generate_image,
        toolset="multimodal",
    )

    register_fn(
        name="synthesize_speech",
        description=(
            "Convert text to speech audio using MiniMax TTS HD. "
            "Saves the audio as an MP3 file and returns the file path. "
            "Useful when the user asks to read text aloud or generate voice messages."
        ),
        schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to convert to speech (max 5000 chars)",
                },
                "voice_id": {
                    "type": "string",
                    "default": "male-qn-qingse",
                    "description": "Voice ID (male-qn-qingse, female-shaonv, etc.)",
                },
            },
            "required": ["text"],
        },
        handler=tool_synthesize_speech,
        toolset="multimodal",
    )


__all__ = ["register_multimodal_tools", "tool_generate_image", "tool_synthesize_speech"]
