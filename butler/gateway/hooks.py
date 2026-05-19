"""Lightweight hook bus for Butler gateway and agent loop."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

HookFn = Callable[..., Any]
_REGISTRY: dict[str, list[HookFn]] = {}


def register_hook(name: str, fn: HookFn) -> None:
    _REGISTRY.setdefault(name, []).append(fn)


def clear_hooks(name: str | None = None) -> None:
    if name is None:
        _REGISTRY.clear()
    else:
        _REGISTRY.pop(name, None)


def invoke_hook(name: str, **kwargs: Any) -> list[Any]:
    results: list[Any] = []
    for fn in _REGISTRY.get(name, []):
        try:
            results.append(fn(**kwargs))
        except Exception as exc:
            logger.warning("Hook %s failed: %s", name, exc)
    return results


def apply_pre_gateway_dispatch(text: str, **ctx: Any) -> str | None:
    """Run pre_gateway_dispatch hooks. Return rewritten text or None to skip."""
    for result in invoke_hook("pre_gateway_dispatch", text=text, **ctx):
        if not isinstance(result, dict):
            continue
        action = result.get("action", "allow")
        if action == "skip":
            return ""
        if action == "rewrite" and result.get("text"):
            text = str(result["text"])
    return text


def apply_pre_llm_context(text: str, **ctx: Any) -> str:
    """Append ephemeral context from pre_llm_call hooks (injected into user message)."""
    parts = [text]
    for result in invoke_hook("pre_llm_call", **ctx):
        if isinstance(result, dict) and result.get("context"):
            parts.append(str(result["context"]))
        elif isinstance(result, str) and result.strip():
            parts.append(result.strip())
    return "\n\n".join(p for p in parts if p)
