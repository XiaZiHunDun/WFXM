"""Lightweight AgentLoop hooks (LangChain AgentMiddleware subset, no LangGraph)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, cast

logger = logging.getLogger(__name__)

MessageDict = dict[str, Any]
ToolDispatch = Callable[[str, MessageDict], str]
BeforeLlmHook = Callable[[list[MessageDict]], list[MessageDict]]
AfterToolsHook = Callable[..., list[MessageDict]]
WrapToolCallHook = Callable[[str, MessageDict, ToolDispatch], str]


class LoopPlugin(Protocol):
    """Optional hooks around model and tool dispatch."""

    def before_model(self, messages: list[MessageDict]) -> list[MessageDict]:
        ...

    def wrap_tool_call(
        self,
        name: str,
        args: MessageDict,
        dispatch: ToolDispatch,
    ) -> str:
        ...


@dataclass
class LoopPluginRegistry:
    plugins: list[Any] = field(default_factory=list)
    _before_llm_hooks: list[BeforeLlmHook] = field(
        default_factory=list, init=False, repr=False, compare=False,
    )
    _after_tools_hooks: list[AfterToolsHook] = field(
        default_factory=list, init=False, repr=False, compare=False,
    )
    _wrap_tool_call_hooks: list[WrapToolCallHook] = field(
        default_factory=list, init=False, repr=False, compare=False,
    )

    def __post_init__(self) -> None:
        for plugin in self.plugins:
            before_hook = getattr(plugin, "before_llm", None) or getattr(plugin, "before_model", None)
            if callable(before_hook):
                self._before_llm_hooks.append(before_hook)
            after_hook = getattr(plugin, "after_tools", None)
            if callable(after_hook):
                self._after_tools_hooks.append(after_hook)
            wrap_hook = getattr(plugin, "wrap_tool_call", None)
            if callable(wrap_hook):
                self._wrap_tool_call_hooks.append(wrap_hook)

    def before_model(self, messages: list[MessageDict]) -> list[MessageDict]:
        from butler.core.loop_plugins_ops import run_plugin_hook_safe

        out = list(messages)
        for hook in self._before_llm_hooks:
            out = run_plugin_hook_safe(
                hook,
                out,
                label="loop_plugins.before_model",
            )
        return out

    def before_llm(self, messages: list[MessageDict]) -> list[MessageDict]:
        return self.before_model(messages)

    def after_tools(
        self,
        messages: list[MessageDict],
        *,
        tool_stats: Any = None,
    ) -> list[MessageDict]:
        from butler.core.loop_plugins_ops import run_plugin_hook_safe

        out = list(messages)
        for hook in reversed(self._after_tools_hooks):
            out = run_plugin_hook_safe(
                hook,
                out,
                label="loop_plugins.after_tools",
                tool_stats=tool_stats,
            )
        return out

    def wrap_tool_call(
        self,
        name: str,
        args: MessageDict,
        dispatch: ToolDispatch,
    ) -> str:
        chain: ToolDispatch = dispatch
        for hook in reversed(self._wrap_tool_call_hooks):
            prev = chain

            def _wrap(
                n: str,
                a: MessageDict,
                _hook: WrapToolCallHook = hook,
                _prev: ToolDispatch = prev,
            ) -> str:
                return _hook(n, a, _prev)

            chain = _wrap
        return chain(name, args)


def default_plugin_registry(config: Any | None = None) -> LoopPluginRegistry:
    from butler.core.loop_middleware import merge_middleware_and_plugins

    plugins: list[Any] = []
    middlewares: list[Any] = []
    if config is not None:
        raw = getattr(config, "plugins", None) or []
        if isinstance(raw, list):
            plugins = list(raw)
        mw = getattr(config, "middlewares", None) or []
        if isinstance(mw, list):
            middlewares = list(mw)
    return cast(
        LoopPluginRegistry,
        merge_middleware_and_plugins(plugins=plugins, middlewares=middlewares),
    )
