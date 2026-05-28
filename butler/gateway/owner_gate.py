"""Owner-only gates for sensitive WeChat commands (e.g. /项目 新建)."""

from __future__ import annotations

import os

from butler.session.keys import chat_id_from_session_key


def _csv_env_ids(name: str) -> list[str]:
    raw = os.getenv(name, "").strip()
    return [part.strip() for part in raw.split(",") if part.strip()]


def resolve_owner_wechat_chat_id() -> str:
    """Primary Owner chat id for runtime push (owner, then active allowlists)."""
    owner = os.getenv("BUTLER_OWNER_WECHAT_ID", "").strip()
    if owner:
        return owner
    for name in ("WECHAT_ALLOWED_USERS", "BUTLER_GATEWAY_ALLOWLIST"):
        ids = _csv_env_ids(name)
        if ids:
            return ids[0]
    return ""


def owner_wechat_ids() -> frozenset[str]:
    """Configured owner / allowlist WeChat user ids."""
    ids: set[str] = set()
    owner = os.getenv("BUTLER_OWNER_WECHAT_ID", "").strip()
    if owner:
        ids.add(owner)
    allow = _csv_env_ids("WECHAT_ALLOWED_USERS")
    if allow:
        ids.update(allow)
        return frozenset(ids)
    legacy = _csv_env_ids("BUTLER_GATEWAY_ALLOWLIST")
    if legacy and not ids:
        ids.update(legacy)
    return frozenset(ids)


def is_gateway_owner(
    *,
    platform: str,
    external_id: str | None = None,
    session_key: str = "",
) -> bool:
    """Return True if the caller may run owner-only gateway actions."""
    if os.getenv("BUTLER_PROJECT_CREATE_OPEN", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return True

    plat = str(platform or "").strip().lower()
    if plat not in ("wechat", "weixin"):
        return True

    allowed = owner_wechat_ids()
    if not allowed:
        return True

    cid = str(external_id or "").strip()
    if not cid and session_key:
        cid = chat_id_from_session_key(session_key)
    return bool(cid and cid in allowed)


def owner_required_message() -> str:
    return (
        "该操作仅主公（Owner）可用。\n"
        "请确认 .env 中已配置 BUTLER_OWNER_WECHAT_ID、WECHAT_ALLOWED_USERS 或 BUTLER_GATEWAY_ALLOWLIST，"
        "且当前微信账号在列表中。\n"
        "开发环境可设 BUTLER_PROJECT_CREATE_OPEN=1 跳过校验。"
    )


__all__ = ["is_gateway_owner", "owner_required_message", "owner_wechat_ids"]
