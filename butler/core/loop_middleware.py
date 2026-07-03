"""LoopMiddleware protocol — DeerFlow-style before_llm / after_tools hooks."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)


class LoopMiddleware(Protocol):
    def before_llm(self, messages: list[dict]) -> list[dict]:
        ...

    def after_tools(
        self,
        messages: list[dict],
        *,
        tool_stats: Any = None,
    ) -> list[dict]:
        ...


@dataclass
class LoopMiddlewareChain:
    middlewares: list[Any] = field(default_factory=list)
    _before_llm_hooks: list[Callable] = field(default_factory=list, init=False, repr=False, compare=False)
    _after_tools_hooks: list[Callable] = field(default_factory=list, init=False, repr=False, compare=False)
    _wrap_tool_call_hooks: list[Callable] = field(default_factory=list, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for mw in self.middlewares:
            before_hook = getattr(mw, "before_llm", None) or getattr(mw, "before_model", None)
            if callable(before_hook):
                self._before_llm_hooks.append(before_hook)
            after_hook = getattr(mw, "after_tools", None)
            if callable(after_hook):
                self._after_tools_hooks.append(after_hook)
            wrap_hook = getattr(mw, "wrap_tool_call", None)
            if callable(wrap_hook):
                self._wrap_tool_call_hooks.append(wrap_hook)

    def before_model(self, messages: list[dict]) -> list[dict]:
        return self.before_llm(messages)

    def before_llm(self, messages: list[dict]) -> list[dict]:
        from butler.core.loop_middleware_ops import run_middleware_hook_safe

        out = list(messages)
        for hook in self._before_llm_hooks:
            out = run_middleware_hook_safe(
                hook,
                out,
                label="loop_middleware.before_llm",
            )
        return out

    def after_tools(
        self,
        messages: list[dict],
        *,
        tool_stats: Any = None,
    ) -> list[dict]:
        from butler.core.loop_middleware_ops import run_middleware_hook_safe

        out = list(messages)
        for hook in reversed(self._after_tools_hooks):
            out = run_middleware_hook_safe(
                hook,
                out,
                label="loop_middleware.after_tools",
                tool_stats=tool_stats,
            )
        return out

    def wrap_tool_call(
        self,
        name: str,
        args: dict,
        dispatch: Callable[[str, dict], str],
    ) -> str:
        chain = dispatch
        for hook in reversed(self._wrap_tool_call_hooks):
            prev = chain

            def _wrap(n: str, a: dict, _hook=hook, _prev=prev) -> str:
                return _hook(n, a, _prev)

            chain = _wrap
        return chain(name, args)


def merge_middleware_and_plugins(
    *,
    plugins: list[Any] | None = None,
    middlewares: list[Any] | None = None,
) -> LoopMiddlewareChain:
    combined: list[Any] = []
    if plugins:
        combined.extend(plugins)
    if middlewares:
        combined.extend(middlewares)
    return LoopMiddlewareChain(middlewares=combined)


__all__ = ["LoopMiddleware", "LoopMiddlewareChain", "merge_middleware_and_plugins"]
