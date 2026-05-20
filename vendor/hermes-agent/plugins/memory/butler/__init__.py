"""Butler layered memory — Hermes MemoryProvider plugin.

Activated via ``memory.provider: butler`` in Hermes config, or by setting
``HERMES_MEMORY_PROVIDER=butler`` before gateway/CLI start.

Surfaces Butler global memory (profile + experience FTS) and optional
project memory (MarkdownMemory + ProjectFacts) into every Hermes
agent turn — both as prefetch context and as ``butler_remember`` /
``butler_recall`` tool schemas.
"""

from .hermes_bridge import HermesButlerMemoryProvider


def register(ctx):
    """Standard Hermes plugin registration."""
    ctx.register_memory_provider(HermesButlerMemoryProvider())
