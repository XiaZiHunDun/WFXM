"""Gateway in-process hook bus for Gateway / AgentLoop.

For shell scripts and Claude Code–compatible hooks, use ``butler.hooks.runner``
(``hooks.yaml``). This module is for Python-only, low-latency context injection.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from butler.gateway.hooks_ops import run_hook_call_safe, run_mutating_hook_safe

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
        result = run_hook_call_safe(name, fn, **kwargs)
        if result is not None:
            results.append(result)
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


def trigger_hooks_mutating(
    name: str,
    input_data: dict[str, Any],
    output_data: dict[str, Any],
) -> dict[str, Any]:
    """Run hooks in order; each may mutate the local copy; return the merged result.

    契约：调用方**必须**使用返回值——``output_data`` 不会被原地变更。
    之所以在内部复制 ``output_data`` 是为了让 hooks 之间不共享中间状态；
    这与 :func:`run_mutating_hook_safe`（live in-place update）契约不同。
    参见 ``docs/architecture/v4-architecture.md §P0-C 静默反模式审计`` 了解
    为什么不要把这里的 ``out = dict(output_data)`` 误改成原地变更。
    """
    out = dict(output_data)
    for fn in _REGISTRY.get(name, []):
        patch = run_mutating_hook_safe(name, fn, input_data, out)
        if isinstance(patch, dict):
            out.update(patch)
    return out


def apply_pre_llm_context(text: str, **ctx: Any) -> str:
    """Append ephemeral context from pre_llm_call hooks (injected into user message)."""
    parts = [text]
    for result in invoke_hook("pre_llm_call", **ctx):
        if isinstance(result, dict) and result.get("context"):
            parts.append(str(result["context"]))
        elif isinstance(result, str) and result.strip():
            parts.append(result.strip())
    return "\n\n".join(p for p in parts if p)
