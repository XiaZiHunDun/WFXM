"""Butler Core — Agent Loop, Orchestrator, and DAG Task Execution."""

from __future__ import annotations

__all__ = [
    "agent_loop",
    "context",
    "compaction",
    "tool",
    "session",
    "llm",
    "loop",
]

from . import agent_loop
from . import context
from . import compaction
from . import tool
from . import session
from . import llm
from . import loop

# Backward compatibility re-exports for split modules
try:
    from .memory_manager import MemoryManager
    from .memory_provider import MemoryProvider
    from .context_scrubber import (
        StreamingContextScrubber,
        build_memory_context_block,
        sanitize_context,
    )
except ImportError:
    pass