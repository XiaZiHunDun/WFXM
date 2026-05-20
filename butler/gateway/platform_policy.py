"""WeChat-only gateway policy (产品仅支持微信网关)."""

from __future__ import annotations

SUPPORTED_PLATFORMS = frozenset({"wechat", "weixin", "微信"})


def normalize_platforms(raw: str) -> list[str]:
    """Parse ``--platforms``; default and only supported value is ``wechat``."""
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


def unsupported_platforms(platforms: list[str]) -> list[str]:
    return [p for p in platforms if p not in SUPPORTED_PLATFORMS]


def format_unsupported_error(unsupported: list[str]) -> str:
    names = ", ".join(unsupported)
    return (
        f"Butler 网关仅支持微信（wechat），当前请求包含: {names}。\n"
        "请使用: butler gateway\n"
        "（无需 --platforms，也请勿配置 telegram 等其他平台。）"
    )
