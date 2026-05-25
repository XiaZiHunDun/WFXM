"""Provider/model quirk table (TradingAgents subset)."""

from __future__ import annotations

from typing import Any

_CAPABILITIES: dict[str, dict[str, Any]] = {
    "anthropic": {
        "supports_thinking": True,
        "tool_choice_style": "anthropic",
        "max_output_default": 8192,
    },
    "openai": {
        "supports_thinking": False,
        "tool_choice_style": "openai",
        "max_output_default": 16384,
    },
    "openrouter": {
        "supports_thinking": False,
        "tool_choice_style": "openai",
        "max_output_default": 16384,
    },
    "minimax": {
        "supports_thinking": False,
        "tool_choice_style": "openai",
        "max_output_default": 8192,
    },
}


def get_provider_capabilities(provider: str) -> dict[str, Any]:
    key = str(provider or "").strip().lower()
    return dict(_CAPABILITIES.get(key) or {"tool_choice_style": "openai"})


def model_supports_thinking(provider: str, model: str = "") -> bool:
    cap = get_provider_capabilities(provider)
    if not cap.get("supports_thinking"):
        return False
    m = str(model or "").strip().lower()
    if m.endswith("-instruct-only") or "no-thinking" in m:
        return False
    return True


def format_capability_hint(provider: str, model: str = "") -> str:
    cap = get_provider_capabilities(provider)
    parts = [f"provider={provider or '?'}"]
    if model:
        parts.append(f"model={model}")
    if cap.get("supports_thinking"):
        parts.append("thinking=on")
    return ", ".join(parts)


__all__ = ["format_capability_hint", "get_provider_capabilities", "model_supports_thinking"]
