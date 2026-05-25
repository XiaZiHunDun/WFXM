"""Lightweight AgentLoop hooks (LangChain AgentMiddleware subset, no LangGraph)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)


class LoopPlugin(Protocol):
    """Optional hooks around model and tool dispatch."""

    def before_model(self, messages: list[dict]) -> list[dict]:
        ...

    def wrap_tool_call(
        self,
        name: str,
        args: dict,
        dispatch: Callable[[str, dict], str],
    ) -> str:
        ...


@dataclass
class LoopPluginRegistry:
    plugins: list[Any] = field(default_factory=list)

    def before_model(self, messages: list[dict]) -> list[dict]:
        out = list(messages)
        for plugin in self.plugins:
            hook = getattr(plugin, "before_llm", None) or getattr(plugin, "before_model", None)
            if not callable(hook):
                continue
            try:
                out = hook(out)
            except Exception as exc:
                logger.debug("loop plugin before_model failed: %s", exc)
        return out

    def before_llm(self, messages: list[dict]) -> list[dict]:
        return self.before_model(messages)

    def after_tools(
        self,
        messages: list[dict],
        *,
        tool_stats: Any = None,
    ) -> list[dict]:
        out = list(messages)
        for plugin in reversed(self.plugins):
            hook = getattr(plugin, "after_tools", None)
            if not callable(hook):
                continue
            try:
                out = hook(out, tool_stats=tool_stats)
            except Exception as exc:
                logger.debug("loop plugin after_tools failed: %s", exc)
        return out

    def wrap_tool_call(
        self,
        name: str,
        args: dict,
        dispatch: Callable[[str, dict], str],
    ) -> str:
        chain = dispatch
        for plugin in reversed(self.plugins):
            hook = getattr(plugin, "wrap_tool_call", None)
            if not callable(hook):
                continue
            prev = chain

            def _wrap(n: str, a: dict, _hook=hook, _prev=prev) -> str:
                return _hook(n, a, _prev)

            chain = _wrap
        return chain(name, args)


def default_plugin_registry(config: Any | None = None) -> LoopPluginRegistry:
    from butler.core.loop_middleware import LoopMiddlewareChain, merge_middleware_and_plugins

    plugins: list[Any] = []
    middlewares: list[Any] = []
    if config is not None:
        raw = getattr(config, "plugins", None) or []
        if isinstance(raw, list):
            plugins = list(raw)
        mw = getattr(config, "middlewares", None) or []
        if isinstance(mw, list):
            middlewares = list(mw)
    return merge_middleware_and_plugins(plugins=plugins, middlewares=middlewares)
