"""Last inbound vision/STT outcomes for /诊断 (no message content logged)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, cast

from butler.config import get_butler_home
import logging

logger = logging.getLogger(__name__)

_STATE_NAME = "runtime/media_telemetry.json"


def _state_path() -> Path:
    return cast(Path, get_butler_home() / _STATE_NAME)


def record_media_event(
    kind: str,
    *,
    provider: str,
    ok: bool,
    duration_ms: float,
    detail: str = "",
) -> None:
    """Persist last event per kind (``vision`` | ``stt``)."""
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    from butler.gateway.media_telemetry_ops import load_json_dict_safe

    data: dict[str, Any] = load_json_dict_safe(path) if path.is_file() else {}
    data[kind] = {
        "provider": (provider or "?")[:40],
        "ok": bool(ok),
        "duration_ms": round(max(0.0, duration_ms), 1),
        "detail": (detail or "")[:120],
        "at": time.time(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")


def load_media_telemetry() -> dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {}
    from butler.gateway.media_telemetry_ops import load_json_dict_safe

    return cast(dict[str, Any], load_json_dict_safe(path))


def format_media_diagnostic_lines() -> list[str]:
    data = load_media_telemetry()
    if not data:
        return []
    lines: list[str] = []
    for kind, label in (("vision", "识图"), ("stt", "语音")):
        row = data.get(kind)
        if not isinstance(row, dict):
            continue
        status = "成功" if row.get("ok") else "失败"
        ms = row.get("duration_ms", "?")
        prov = row.get("provider") or "?"
        extra = f" ({row['detail']})" if row.get("detail") else ""
        lines.append(f"  上次{label}: {prov} {status} {ms}ms{extra}")
    return lines
