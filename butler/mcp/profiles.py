"""MCP server profile routing (awesome-llm-apps multi_mcp_agent_router subset)."""

from __future__ import annotations

import logging
import re
import threading

import yaml

from butler.env_parse import env_truthy
from butler.mcp.config import _resolve_config_paths
from butler.mcp.types import McpServerConfig

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_PROFILES: dict[str, list[str]] | None = None
_ROUTING: list[tuple[str, list[str]]] = []
_SESSION_PROFILE: dict[str, str] = {}


def mcp_profiles_enabled() -> bool:
    return env_truthy("BUTLER_MCP_PROFILES", default=True)


def _load_profile_config() -> tuple[dict[str, list[str]], list[tuple[str, list[str]]]]:
    profiles: dict[str, list[str]] = {"default": []}
    routing: list[tuple[str, list[str]]] = []
    for path in _resolve_config_paths(None):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.debug("MCP profiles config %s: %s", path, exc)
            continue
        if not isinstance(data, dict):
            continue
        block = data.get("profiles")
        if isinstance(block, dict):
            for name, servers in block.items():
                key = str(name or "").strip().lower()
                if not key:
                    continue
                if isinstance(servers, list):
                    profiles[key] = [str(s).strip() for s in servers if str(s).strip()]
        route_block = data.get("mcp_profile_routing") or data.get("profile_routing")
        if isinstance(route_block, dict):
            for prof, kws in route_block.items():
                pname = str(prof or "").strip().lower()
                if not pname:
                    continue
                if isinstance(kws, list):
                    routing.append((pname, [str(k).lower() for k in kws if str(k).strip()]))
                elif isinstance(kws, str):
                    routing.append((pname, [k.strip().lower() for k in kws.split(",") if k.strip()]))
    if "default" not in profiles or not profiles["default"]:
        profiles["default"] = list(profiles.get("all", []) or [])
    return profiles, routing


def _ensure_loaded() -> None:
    global _PROFILES, _ROUTING
    with _LOCK:
        if _PROFILES is None:
            _PROFILES, _ROUTING = _load_profile_config()


def list_profile_names() -> list[str]:
    _ensure_loaded()
    assert _PROFILES is not None
    return sorted(_PROFILES.keys())


def select_profile_for_text(text: str, *, default: str = "default") -> str:
    """Keyword routing to profile name."""
    if not mcp_profiles_enabled():
        return default
    _ensure_loaded()
    body = (text or "").strip().lower()
    if not body:
        return get_session_profile(default=default)
    for pname, keywords in _ROUTING:
        for kw in keywords:
            if not kw:
                continue
            if re.search(rf"(?<![\w]){re.escape(kw)}(?![\w])", body, re.UNICODE) or kw in body:
                return pname
    return default


def set_session_profile(session_key: str, profile: str) -> None:
    sk = str(session_key or "default").strip() or "default"
    with _LOCK:
        _SESSION_PROFILE[sk] = str(profile or "default").strip().lower() or "default"


def get_session_profile(*, session_key: str = "", default: str = "default") -> str:
    sk = str(session_key or "").strip() or "default"
    with _LOCK:
        return _SESSION_PROFILE.get(sk, default)


def filter_servers_by_profile(
    configs: list[McpServerConfig],
    profile: str,
) -> list[McpServerConfig]:
    if not mcp_profiles_enabled():
        return configs
    _ensure_loaded()
    assert _PROFILES is not None
    pname = str(profile or "default").strip().lower() or "default"
    allowed = _PROFILES.get(pname)
    if not allowed:
        allowed = _PROFILES.get("default")
    if not allowed:
        return configs
    allow_set = {str(s).strip() for s in allowed}
    filtered = [c for c in configs if c.server_id in allow_set]
    return filtered if filtered else configs


__all__ = [
    "filter_servers_by_profile",
    "get_session_profile",
    "list_profile_names",
    "mcp_profiles_enabled",
    "select_profile_for_text",
    "set_session_profile",
]
