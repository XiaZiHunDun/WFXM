"""Gateway inbound-media settings: ``config.yaml`` gateway section with env overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml

from butler.config import get_butler_settings


from butler.defaults.env_defaults import (
    GATEWAY_DEFAULT_QUEUE_DROP,
    GATEWAY_DEFAULT_QUEUE_MODE,
    GATEWAY_QUEUE_CAP,
    GATEWAY_QUEUE_COLLECT_DEBOUNCE_MS,
)
from butler.defaults.model_defaults import (
    GATEWAY_VISION_ENDPOINT,
    GATEWAY_VISION_PROVIDER,
    GATEWAY_WHISPER_MODEL,
)

_VALID_QUEUE_MODES = frozenset({"followup", "collect", "interrupt", "steer"})
_VALID_QUEUE_DROP = frozenset({"summarize", "old", "new"})


@dataclass
class GatewayVisionConfig:
    provider: str = GATEWAY_VISION_PROVIDER
    api_host: str = ""
    endpoint: str = GATEWAY_VISION_ENDPOINT
    timeout_seconds: float = 45.0


@dataclass
class GatewaySpeechConfig:
    prefer_ilink_text: bool = True
    stt_provider: str = "local"
    whisper_model: str = GATEWAY_WHISPER_MODEL


@dataclass
class GatewayInboundConfig:
    enabled: bool = True
    max_chars: int = 3000
    vision: GatewayVisionConfig = field(default_factory=GatewayVisionConfig)
    speech: GatewaySpeechConfig = field(default_factory=GatewaySpeechConfig)
    yaml_configured: bool = False


@dataclass
class GatewayQueueConfig:
    mode: str = GATEWAY_DEFAULT_QUEUE_MODE
    cap: int = GATEWAY_QUEUE_CAP
    drop: str = GATEWAY_DEFAULT_QUEUE_DROP
    collect_debounce_ms: int = GATEWAY_QUEUE_COLLECT_DEBOUNCE_MS
    yaml_configured: bool = False


def _bool_env(name: str, default: bool) -> bool:
    from butler.env_parse import env_truthy

    return env_truthy(name, default=default)


def _load_yaml_gateway() -> dict[str, Any]:
    settings = get_butler_settings()
    path = settings.config_yaml_path
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    gw = data.get("gateway")
    return gw if isinstance(gw, dict) else {}


def resolve_gateway_inbound_config() -> GatewayInboundConfig:
    """Merge ``config.yaml`` gateway.inbound_media with env (env wins)."""
    raw = _load_yaml_gateway()
    if isinstance(raw.get("inbound_media"), dict):
        yaml_configured = True
        inbound = raw["inbound_media"]
    else:
        legacy_keys = {k for k in raw if k != "queue"}
        yaml_configured = bool(legacy_keys)
        inbound = raw if yaml_configured else {}
    if not isinstance(inbound, dict):
        inbound = {}

    vision_raw = inbound.get("vision") if isinstance(inbound.get("vision"), dict) else {}
    speech_raw = inbound.get("speech") if isinstance(inbound.get("speech"), dict) else {}

    enabled_default = True
    if "enabled" in inbound:
        enabled_default = bool(inbound["enabled"])
    enabled = _bool_env("BUTLER_WECHAT_INBOUND_MEDIA", enabled_default)

    from butler.env_parse import int_env

    try:
        yaml_max = int(inbound.get("max_chars", 3000))
    except (TypeError, ValueError):
        yaml_max = 3000
    max_chars = int_env("BUTLER_WECHAT_MEDIA_MAX_CHARS", yaml_max, min=500)

    v_host = (
        os.getenv("BUTLER_WECHAT_MINIMAX_API_HOST", "").strip()
        or os.getenv("MINIMAX_API_HOST", "").strip()
        or str(vision_raw.get("api_host") or "").strip()
    )
    v_endpoint = str(vision_raw.get("endpoint") or GATEWAY_VISION_ENDPOINT).strip().lstrip("/")
    from butler.env_parse import float_env

    try:
        yaml_timeout = float(vision_raw.get("timeout_seconds", 45))
    except (TypeError, ValueError):
        yaml_timeout = 45.0
    v_timeout = float_env("BUTLER_WECHAT_VISION_TIMEOUT", yaml_timeout, min=1.0)

    prefer_ilink = speech_raw.get("prefer_ilink_text", True)
    if os.getenv("BUTLER_WECHAT_PREFER_ILINK_TEXT", "").strip():
        prefer_ilink = _bool_env("BUTLER_WECHAT_PREFER_ILINK_TEXT", bool(prefer_ilink))

    stt = (
        os.getenv("BUTLER_WECHAT_STT_PROVIDER", "").strip()
        or str(speech_raw.get("stt_provider") or "local").strip()
        or "local"
    )
    whisper = (
        os.getenv("BUTLER_WECHAT_WHISPER_MODEL", "").strip()
        or str(speech_raw.get("whisper_model") or GATEWAY_WHISPER_MODEL).strip()
        or GATEWAY_WHISPER_MODEL
    )

    return GatewayInboundConfig(
        enabled=enabled,
        max_chars=max_chars,
        vision=GatewayVisionConfig(
            provider=str(vision_raw.get("provider") or GATEWAY_VISION_PROVIDER).strip(),
            api_host=v_host,
            endpoint=v_endpoint,
            timeout_seconds=v_timeout,
        ),
        speech=GatewaySpeechConfig(
            prefer_ilink_text=bool(prefer_ilink),
            stt_provider=stt.lower(),
            whisper_model=whisper,
        ),
        yaml_configured=yaml_configured,
    )


def format_gateway_inbound_config_source_line() -> str:
    """One-line effective inbound-media summary for ``/诊断``."""
    cfg = resolve_gateway_inbound_config()
    source = "yaml+env" if cfg.yaml_configured else "env/默认"
    if not cfg.enabled:
        return f"  入站媒体: 关, 来源={source}"
    return (
        f"  入站媒体: 开, max_chars={cfg.max_chars}, "
        f"VLM={cfg.vision.provider}/{cfg.vision.endpoint}, "
        f"STT={cfg.speech.stt_provider}/{cfg.speech.whisper_model}, "
        f"来源={source}"
    )


def _queue_mode_from_raw(raw: dict[str, Any]) -> str:
    mode = str(raw.get("mode") or GATEWAY_DEFAULT_QUEUE_MODE).strip().lower()
    return mode if mode in _VALID_QUEUE_MODES else GATEWAY_DEFAULT_QUEUE_MODE


def _queue_cap_from_raw(raw: dict[str, Any]) -> int:
    if "cap" not in raw:
        return GATEWAY_QUEUE_CAP
    try:
        return max(1, int(raw["cap"]))
    except (TypeError, ValueError):
        return GATEWAY_QUEUE_CAP


def _queue_drop_from_raw(raw: dict[str, Any]) -> str:
    drop = str(raw.get("drop") or GATEWAY_DEFAULT_QUEUE_DROP).strip().lower()
    return drop if drop in _VALID_QUEUE_DROP else GATEWAY_DEFAULT_QUEUE_DROP


def _queue_debounce_from_raw(raw: dict[str, Any]) -> int:
    if "collect_debounce_ms" not in raw:
        return GATEWAY_QUEUE_COLLECT_DEBOUNCE_MS
    try:
        return max(0, int(raw["collect_debounce_ms"]))
    except (TypeError, ValueError):
        return GATEWAY_QUEUE_COLLECT_DEBOUNCE_MS


def resolve_gateway_queue_config() -> GatewayQueueConfig:
    """Merge ``config.yaml`` ``gateway.queue`` with env (env wins)."""
    raw_gw = _load_yaml_gateway()
    yaml_configured = isinstance(raw_gw.get("queue"), dict)
    queue_raw = raw_gw["queue"] if yaml_configured else {}

    yaml_mode = _queue_mode_from_raw(queue_raw)
    yaml_cap = _queue_cap_from_raw(queue_raw)
    yaml_drop = _queue_drop_from_raw(queue_raw)
    yaml_debounce = _queue_debounce_from_raw(queue_raw)

    mode_raw = (
        os.getenv("BUTLER_GATEWAY_QUEUE_MODE", yaml_mode) or yaml_mode
    ).strip().lower()
    mode = mode_raw if mode_raw in _VALID_QUEUE_MODES else GATEWAY_DEFAULT_QUEUE_MODE

    from butler.env_parse import int_env

    cap = int_env("BUTLER_GATEWAY_QUEUE_CAP", yaml_cap, min=1)

    drop_raw = (
        os.getenv("BUTLER_GATEWAY_QUEUE_DROP", yaml_drop) or yaml_drop
    ).strip().lower()
    drop = drop_raw if drop_raw in _VALID_QUEUE_DROP else GATEWAY_DEFAULT_QUEUE_DROP

    debounce_default = str(yaml_debounce)
    try:
        debounce = max(
            0,
            int(
                os.getenv("BUTLER_GATEWAY_QUEUE_COLLECT_DEBOUNCE_MS", debounce_default)
                or debounce_default
            ),
        )
    except ValueError:
        debounce = yaml_debounce

    return GatewayQueueConfig(
        mode=mode,
        cap=cap,
        drop=drop,
        collect_debounce_ms=debounce,
        yaml_configured=yaml_configured,
    )


def format_gateway_queue_config_source_line() -> str:
    """One-line effective global queue summary for ``/诊断``."""
    cfg = resolve_gateway_queue_config()
    source = "yaml+env" if cfg.yaml_configured else "env/默认"
    return (
        f"  入站队列(全局): mode={cfg.mode}, cap={cfg.cap}, drop={cfg.drop}, "
        f"debounce={cfg.collect_debounce_ms}ms, 来源={source}"
    )


def vision_api_host() -> str:
    """Resolved MiniMax API host for VLM (env > yaml > MINIMAX_BASE_URL)."""
    cfg = resolve_gateway_inbound_config()
    if cfg.vision.api_host:
        host = cfg.vision.api_host.rstrip("/")
        if host.endswith("/v1"):
            return host[:-3].rstrip("/")
        return host
    explicit = os.getenv("MINIMAX_API_HOST", "").strip()
    if explicit:
        return explicit.rstrip("/")
    base = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1").strip().rstrip("/")
    if base.endswith("/v1"):
        return base[:-3].rstrip("/")
    return base


def vision_endpoint_path() -> str:
    ep = resolve_gateway_inbound_config().vision.endpoint or "coding_plan/vlm"
    return ep.lstrip("/")


__all__ = [
    "GatewayInboundConfig",
    "GatewayQueueConfig",
    "GatewaySpeechConfig",
    "GatewayVisionConfig",
    "format_gateway_inbound_config_source_line",
    "format_gateway_queue_config_source_line",
    "resolve_gateway_inbound_config",
    "resolve_gateway_queue_config",
    "vision_api_host",
    "vision_endpoint_path",
]
