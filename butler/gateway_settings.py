"""Gateway inbound-media settings: ``config.yaml`` gateway section with env overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml

from butler.config import get_butler_settings


@dataclass
class GatewayVisionConfig:
    provider: str = "minimax"
    api_host: str = ""
    endpoint: str = "coding_plan/vlm"
    timeout_seconds: float = 45.0


@dataclass
class GatewaySpeechConfig:
    prefer_ilink_text: bool = True
    stt_provider: str = "local"
    whisper_model: str = "small"


@dataclass
class GatewayInboundConfig:
    enabled: bool = True
    max_chars: int = 3000
    vision: GatewayVisionConfig = field(default_factory=GatewayVisionConfig)
    speech: GatewaySpeechConfig = field(default_factory=GatewaySpeechConfig)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


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
    inbound = raw.get("inbound_media") if isinstance(raw.get("inbound_media"), dict) else raw
    if not isinstance(inbound, dict):
        inbound = {}

    vision_raw = inbound.get("vision") if isinstance(inbound.get("vision"), dict) else {}
    speech_raw = inbound.get("speech") if isinstance(inbound.get("speech"), dict) else {}

    enabled_default = True
    if "enabled" in inbound:
        enabled_default = bool(inbound["enabled"])
    enabled = _bool_env("BUTLER_WECHAT_INBOUND_MEDIA", enabled_default)

    max_chars = 3000
    try:
        max_chars = max(500, int(os.getenv("BUTLER_WECHAT_MEDIA_MAX_CHARS", str(inbound.get("max_chars", 3000)))))
    except (TypeError, ValueError):
        pass

    v_host = (
        os.getenv("BUTLER_WECHAT_MINIMAX_API_HOST", "").strip()
        or os.getenv("MINIMAX_API_HOST", "").strip()
        or str(vision_raw.get("api_host") or "").strip()
    )
    v_endpoint = str(vision_raw.get("endpoint") or "coding_plan/vlm").strip().lstrip("/")
    try:
        v_timeout = float(
            os.getenv(
                "BUTLER_WECHAT_VISION_TIMEOUT",
                str(vision_raw.get("timeout_seconds", 45)),
            )
        )
    except (TypeError, ValueError):
        v_timeout = 45.0

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
        or str(speech_raw.get("whisper_model") or "small").strip()
        or "small"
    )

    return GatewayInboundConfig(
        enabled=enabled,
        max_chars=max_chars,
        vision=GatewayVisionConfig(
            provider=str(vision_raw.get("provider") or "minimax").strip(),
            api_host=v_host,
            endpoint=v_endpoint,
            timeout_seconds=v_timeout,
        ),
        speech=GatewaySpeechConfig(
            prefer_ilink_text=bool(prefer_ilink),
            stt_provider=stt.lower(),
            whisper_model=whisper,
        ),
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
    "GatewaySpeechConfig",
    "GatewayVisionConfig",
    "resolve_gateway_inbound_config",
    "vision_api_host",
    "vision_endpoint_path",
]
