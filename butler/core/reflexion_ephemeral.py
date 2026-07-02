"""Ephemeral reflexion banner after repeated tool failures (PEG subset)."""

from __future__ import annotations

from typing import Any

from butler.env_parse import env_truthy


def reflexion_ephemeral_enabled() -> bool:
    return env_truthy("BUTLER_REFLEXION_EPHEMERAL", default=False)


def build_reflexion_banner(
    *,
    tool_name: str,
    failure_count: int,
    last_error: str = "",
) -> str:
    if not reflexion_ephemeral_enabled() or failure_count < 2:
        return ""
    err = str(last_error or "").strip()[:200]
    return (
        "## Reflexion（ephemeral）\n"
        f"工具 `{tool_name}` 已连续失败 {failure_count} 次。"
        + (f" 最近错误: {err}" if err else "")
        + " 请换策略或向用户说明阻塞，勿重复相同调用。"
    )


def maybe_apply_reflexion(
    diagnostics: dict[str, Any] | None,
    *,
    tool_name: str,
    failure_count: int,
    last_error: str = "",
) -> None:
    if not isinstance(diagnostics, dict):
        return
    banner = build_reflexion_banner(
        tool_name=tool_name,
        failure_count=failure_count,
        last_error=last_error,
    )
    if banner:
        diagnostics["ephemeral_system"] = banner
    from butler.core.reflexion_ephemeral_ops import persist_reflexion_episode_safe
    from butler.execution_context import get_current_session_key

    persist_reflexion_episode_safe(
        tool_name=tool_name,
        failure_count=failure_count,
        last_error=last_error,
        session_key=str(get_current_session_key() or ""),
    )
__all__ = [
    "build_reflexion_banner",
    "maybe_apply_reflexion",
    "reflexion_ephemeral_enabled",
]
