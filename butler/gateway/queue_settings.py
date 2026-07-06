"""Per-session gateway inbound queue mode (OpenClaw-style, zero deps)."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, cast

from butler.config import get_butler_home
from butler.gateway_settings import resolve_gateway_queue_config

_VALID_MODES = frozenset({"followup", "collect", "interrupt", "steer"})
_VALID_DROP = frozenset({"summarize", "old", "new"})
_LOCK = threading.RLock()
_OVERRIDES: dict[str, dict[str, Any]] = {}


def _settings_dir() -> Path:
    path = get_butler_home() / "gateway_queue"
    path.mkdir(parents=True, exist_ok=True)
    return cast(Path, path)


def _override_path(session_key: str) -> Path:
    import hashlib

    digest = hashlib.sha256(str(session_key or "default").encode("utf-8")).hexdigest()[:16]
    return _settings_dir() / f"{digest}.json"


def _load_override_file(session_key: str) -> dict[str, Any]:
    from butler.gateway.queue_settings_ops import load_queue_override_safe

    return cast(dict[str, Any], load_queue_override_safe(_override_path(session_key)))


def _save_override_file(session_key: str, data: dict[str, Any]) -> None:
    path = _override_path(session_key)
    if not data:
        path.unlink(missing_ok=True)
        with _LOCK:
            _OVERRIDES.pop(str(session_key or "default"), None)
        return
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with _LOCK:
        _OVERRIDES[str(session_key or "default")] = dict(data)


def get_session_override(session_key: str) -> dict[str, Any]:
    key = str(session_key or "default")
    with _LOCK:
        cached = _OVERRIDES.get(key)
    if cached is not None:
        return dict(cached)
    loaded = _load_override_file(key)
    with _LOCK:
        _OVERRIDES[key] = loaded
    return dict(loaded)


def clear_session_override(session_key: str) -> None:
    _save_override_file(session_key, {})


def default_queue_mode() -> str:
    return cast(str, resolve_gateway_queue_config().mode)


def get_queue_mode(session_key: str) -> str:
    override = get_session_override(session_key)
    mode = str(override.get("mode") or "").strip().lower()
    if mode in _VALID_MODES:
        return mode
    return default_queue_mode()


def queue_cap() -> int:
    return cast(int, resolve_gateway_queue_config().cap)


def queue_drop_policy() -> str:
    return cast(str, resolve_gateway_queue_config().drop)


def session_queue_cap(session_key: str) -> int:
    override = get_session_override(session_key)
    if override.get("cap") is not None:
        try:
            return max(1, int(override["cap"]))
        except (TypeError, ValueError):
            pass
    return queue_cap()


def session_drop_policy(session_key: str) -> str:
    override = get_session_override(session_key)
    drop = str(override.get("drop") or "").strip().lower()
    if drop in _VALID_DROP:
        return drop
    return queue_drop_policy()


def collect_debounce_ms(session_key: str) -> int:
    override = get_session_override(session_key)
    if override.get("debounce_ms") is not None:
        try:
            return max(0, int(override["debounce_ms"]))
        except (TypeError, ValueError):
            pass
    return cast(int, resolve_gateway_queue_config().collect_debounce_ms)


def _parse_duration_ms(token: str) -> int | None:
    token = (token or "").strip().lower()
    if not token:
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(ms|s|m)?", token)
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2) or "ms"
    if unit == "s":
        return int(value * 1000)
    if unit == "m":
        return int(value * 60_000)
    return int(value)


def parse_queue_command(arg: str) -> tuple[str | None, dict[str, Any], str | None]:
    """Parse ``/queue steer|followup|collect|interrupt`` and options."""
    stripped = (arg or "").strip()
    if not stripped:
        return None, {}, "用法：/queue followup|collect|interrupt|steer [cap:N] [drop:summarize] [debounce:500ms]"
    if stripped.lower() in ("/queue", "default", "reset"):
        return "reset", {}, None

    parts = stripped.split()
    mode_token = parts[0].lower()
    if mode_token not in _VALID_MODES and mode_token != "reset":
        return None, {}, f"未知模式：{mode_token}（可选 followup、collect、interrupt、steer）"

    opts: dict[str, Any] = {}
    for token in parts[1:]:
        lower = token.lower()
        if lower.startswith("cap:"):
            try:
                opts["cap"] = max(1, int(lower.split(":", 1)[1]))
            except ValueError:
                return None, {}, f"无效 cap：{token}"
        elif lower.startswith("drop:"):
            drop = lower.split(":", 1)[1]
            if drop not in _VALID_DROP:
                return None, {}, f"无效 drop：{drop}"
            opts["drop"] = drop
        elif lower.startswith("debounce:"):
            ms = _parse_duration_ms(lower.split(":", 1)[1])
            if ms is None:
                return None, {}, f"无效 debounce：{token}"
            opts["debounce_ms"] = ms
        else:
            return None, {}, f"未知选项：{token}"

    if mode_token == "reset":
        return "reset", opts, None
    return mode_token, opts, None


def apply_queue_command(session_key: str, arg: str) -> str:
    mode, opts, err = parse_queue_command(arg)
    if err:
        return err
    if mode == "reset":
        clear_session_override(session_key)
        return f"已恢复入站队列默认（全局模式 {default_queue_mode()}，cap={queue_cap()}）。"

    data = get_session_override(session_key)
    data["mode"] = mode
    data.update(opts)
    _save_override_file(session_key, data)
    bits = [f"模式={mode}"]
    if "cap" in opts:
        bits.append(f"cap={opts['cap']}")
    if "drop" in opts:
        bits.append(f"drop={opts['drop']}")
    if "debounce_ms" in opts:
        bits.append(f"debounce={opts['debounce_ms']}ms")
    return f"本会话入站队列：{' · '.join(bits)}。"


def format_queue_status_line(session_key: str) -> str:
    override = get_session_override(session_key)
    mode = get_queue_mode(session_key)
    cap = session_queue_cap(session_key)
    drop = session_drop_policy(session_key)
    debounce = collect_debounce_ms(session_key)
    src = "会话覆盖" if override.get("mode") else "全局默认"
    return (
        f"入站队列: {mode} (cap={cap}, drop={drop}, debounce={debounce}ms, {src})"
    )
