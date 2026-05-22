"""Butler layered memory: global (Butler) and per-project scopes."""

from butler.memory.butler_memory import ButlerMemory
from butler.memory.project_memory import ProjectMemory
from butler.memory.semantic_config import semantic_memory_enabled
from butler.memory.semantic_index import SemanticMemoryIndex

__all__ = [
    "ButlerMemory",
    "ButlerMemoryProvider",
    "ButlerMemoryService",
    "ProjectMemory",
    "SemanticMemoryIndex",
    "semantic_memory_enabled",
]


def __getattr__(name: str):
    if name in ("ButlerMemoryService", "ButlerMemoryProvider"):
        from butler.memory.facade import ButlerMemoryProvider, ButlerMemoryService

        return ButlerMemoryService if name == "ButlerMemoryService" else ButlerMemoryProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
