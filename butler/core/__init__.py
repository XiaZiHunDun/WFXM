"""Butler Core — Agent Loop, Orchestrator, and DAG Task Execution.

Uses lazy imports via ``__getattr__`` to defer sub-package loading until
first access, preventing the 546-module cascade on initial import.
"""

from __future__ import annotations

__all__ = [
    "agent_loop",
    "context",
    "compaction",
    "tool",
    "session",
    "llm",
    "loop",
    "effects",
    "events",
    "adt",
    "validation",
    "MemoryManager",
    "MemoryProvider",
    "StreamingContextScrubber",
    "build_memory_context_block",
    "sanitize_context",
]

_SUBMODULES = frozenset(__all__[:11])

_lazy_imported: dict[str, object] = {}


def __getattr__(name: str) -> object:
    if name in _SUBMODULES:
        if name not in _lazy_imported:
            mod = __import__(f"butler.core.{name}", fromlist=[name])
            _lazy_imported[name] = mod
        return _lazy_imported[name]

    if name in {"MemoryManager", "MemoryProvider"}:
        from butler.core.memory_manager import MemoryManager
        from butler.core.memory_provider import MemoryProvider
        globals()["MemoryManager"] = MemoryManager
        globals()["MemoryProvider"] = MemoryProvider
        return globals()[name]

    if name in {"StreamingContextScrubber", "build_memory_context_block", "sanitize_context"}:
        from butler.core.context_scrubber import (
            StreamingContextScrubber,
            build_memory_context_block,
            sanitize_context,
        )
        globals()["StreamingContextScrubber"] = StreamingContextScrubber
        globals()["build_memory_context_block"] = build_memory_context_block
        globals()["sanitize_context"] = sanitize_context
        return globals()[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + __all__)