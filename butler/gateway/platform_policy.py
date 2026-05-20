"""Gateway platform routing: Butler-native vs Hermes subprocess fallback."""

from __future__ import annotations

import importlib.util
from typing import Literal

# 日常主路径：微信。其余平台走 Hermes 子进程（简单解耦，不做全量提炼）。
NATIVE_PLATFORMS = frozenset({"wechat", "weixin", "微信"})

GatewayRoute = Literal["native", "hermes", "mixed_error"]


def normalize_platforms(raw: str) -> list[str]:
    if not (raw or "").strip():
        return ["wechat"]
    out: list[str] = []
    for part in raw.replace(",", " ").split():
        name = part.strip().lower()
        if name in ("微信", "weixin"):
            name = "wechat"
        if name and name not in out:
            out.append(name)
    return out or ["wechat"]


def partition_platforms(platforms: list[str]) -> tuple[list[str], list[str]]:
    native = [p for p in platforms if p in NATIVE_PLATFORMS]
    hermes = [p for p in platforms if p not in NATIVE_PLATFORMS]
    return native, hermes


def resolve_gateway_route(platforms: list[str]) -> GatewayRoute:
    native, hermes = partition_platforms(platforms)
    if native and hermes:
        return "mixed_error"
    if hermes:
        return "hermes"
    return "native"


def hermes_vendored_installed() -> bool:
    """True when ``pip install -e '.[hermes-gateway]'`` (or hermes-vendored) is present."""
    try:
        return importlib.util.find_spec("hermes_cli") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def format_mixed_platform_error(platforms: list[str]) -> str:
    native, hermes = partition_platforms(platforms)
    return (
        f"不能在同一进程混用 Butler 原生平台（{', '.join(native)}）"
        f"与 Hermes 平台（{', '.join(hermes)}）。\n"
        f"  微信：butler gateway\n"
        f"  其他：butler gateway --platforms {hermes[0]}"
        "（将自动走 Hermes 子进程）"
    )


def format_hermes_install_hint(hermes_platforms: list[str]) -> str:
    names = ", ".join(hermes_platforms)
    return (
        f"平台 {names} 需要 Hermes 子进程网关，但未安装 hermes-vendored。\n"
        "请执行: pip install -e \".[hermes-gateway]\"\n"
        "然后: butler gateway --platforms " + (hermes_platforms[0] if len(hermes_platforms) == 1 else names)
    )
