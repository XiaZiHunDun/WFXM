"""Optional progressive WeChat replies during long streams (Hermes GatewayStream subset)."""

from __future__ import annotations

import os
import time

from butler.env_parse import env_truthy


def progressive_stream_enabled() -> bool:
    return env_truthy("BUTLER_GATEWAY_PROGRESSIVE_STREAM", default=False)


def progressive_stream_min_chars() -> int:
    try:
        return max(80, int(os.getenv("BUTLER_GATEWAY_PROGRESSIVE_MIN_CHARS", "240")))
    except ValueError:
        return 240


def progressive_stream_interval_seconds() -> float:
    try:
        return max(15.0, float(os.getenv("BUTLER_GATEWAY_PROGRESSIVE_INTERVAL", "45")))
    except ValueError:
        return 45.0


def format_progressive_chunk(preview: str) -> str:
    body = (preview or "").strip()
    if len(body) > 320:
        body = body[:317] + "..."
    if not body:
        return ""
    return f"⏳ 处理中…\n{body}"


def maybe_schedule_progressive_reply(bridge: object | None, preview: str) -> None:
    """Rate-limited supplementary message while the main reply is still generating."""
    if bridge is None or not progressive_stream_enabled():
        return
    text = format_progressive_chunk(preview)
    if not text:
        return
    now = time.monotonic()
    last = float(getattr(bridge, "_progressive_last_at", 0.0) or 0.0)
    if now - last < progressive_stream_interval_seconds():
        return
    chars = int(getattr(bridge, "_stream_chars", 0) or 0)
    if chars < progressive_stream_min_chars():
        return
    schedule = getattr(bridge, "schedule_supplementary_reply", None)
    if not callable(schedule):
        return
    if schedule(text, kind="progressive_stream"):
        bridge._progressive_last_at = now  # type: ignore[attr-defined]
