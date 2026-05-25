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

    def before_model(self, messages: list[dict]) -> list[dict]:
        return self.before_llm(messages)

    def before_llm(self, messages: list[dict]) -> list[dict]:
        out = list(messages)
        for mw in self.middlewares:
            hook = getattr(mw, "before_llm", None) or getattr(mw, "before_model", None)
            if not callable(hook):
                continue
            try:
                out = hook(out)
            except Exception as exc:
                logger.debug("loop middleware before_llm failed: %s", exc)
        return out

    def after_tools(
        self,
        messages: list[dict],
        *,
        tool_stats: Any = None,
    ) -> list[dict]:
        out = list(messages)
        for mw in reversed(self.middlewares):
            hook = getattr(mw, "after_tools", None)
            if not callable(hook):
                continue
            try:
                out = hook(out, tool_stats=tool_stats)
            except Exception as exc:
                logger.debug("loop middleware after_tools failed: %s", exc)
        return out

    def wrap_tool_call(
        self,
        name: str,
        args: dict,
        dispatch: Callable[[str, dict], str],
    ) -> str:
        chain = dispatch
        for mw in reversed(self.middlewares):
            hook = getattr(mw, "wrap_tool_call", None)
            if not callable(hook):
                continue
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
