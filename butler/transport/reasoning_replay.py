"""Reasoning echo-back for DeepSeek/Kimi thinking-mode APIs (Hermes run_agent L9734+)."""

from __future__ import annotations

from typing import Any


def _host_matches(base_url: str | None, host_suffix: str) -> bool:
    if not base_url:
        return False
    from butler.transport.reasoning_replay_ops import parse_url_hostname_safe

    host = parse_url_hostname_safe(base_url)
    return host == host_suffix or host.endswith("." + host_suffix)


def needs_thinking_reasoning_pad(
    provider: str = "",
    model: str = "",
    base_url: str | None = None,
) -> bool:
    """True when provider requires reasoning_content on assistant replay."""
    return needs_deepseek_tool_reasoning(provider, model, base_url) or needs_kimi_tool_reasoning(
        provider, model, base_url
    )


def needs_deepseek_tool_reasoning(
    provider: str = "",
    model: str = "",
    base_url: str | None = None,
) -> bool:
    p = (provider or "").lower()
    m = (model or "").lower()
    return (
        p == "deepseek"
        or "deepseek" in m
        or _host_matches(base_url, "api.deepseek.com")
    )


def needs_kimi_tool_reasoning(
    provider: str = "",
    model: str = "",
    base_url: str | None = None,
) -> bool:
    p = (provider or "").lower()
    return (
        p in {"kimi-coding", "kimi-coding-cn", "kimi", "moonshot"}
        or _host_matches(base_url, "api.kimi.com")
        or _host_matches(base_url, "moonshot.ai")
        or _host_matches(base_url, "moonshot.cn")
    )


def apply_reasoning_for_api(
    source: dict[str, Any],
    api_msg: dict[str, Any],
    *,
    provider: str = "",
    model: str = "",
    base_url: str | None = None,
) -> None:
    """Copy reasoning fields onto outbound API messages for thinking providers."""
    if source.get("role") != "assistant":
        return

    needs_pad = needs_thinking_reasoning_pad(provider, model, base_url)
    existing = source.get("reasoning_content")

    if isinstance(existing, str):
        if existing == "" and needs_pad:
            api_msg["reasoning_content"] = " "
        else:
            api_msg["reasoning_content"] = existing
        return

    normalized = source.get("reasoning")
    if (
        needs_pad
        and source.get("tool_calls")
        and isinstance(normalized, str)
        and normalized
    ):
        api_msg["reasoning_content"] = " "
        return

    if isinstance(normalized, str) and normalized:
        api_msg["reasoning_content"] = normalized
        return

    if needs_pad:
        api_msg["reasoning_content"] = " "
        return

    api_msg.pop("reasoning_content", None)


def store_reasoning_on_message(msg: dict[str, Any], reasoning: str | None) -> None:
    """Persist reasoning on in-session assistant messages for later API replay."""
    if not reasoning:
        return
    msg["reasoning"] = reasoning
    msg.setdefault("reasoning_content", reasoning)
