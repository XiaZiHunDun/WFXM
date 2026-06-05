"""Backward-compat re-export — the interrupt primitive moved to core.

The interrupt signal (thread-local set guarded by a lock) has no tool
semantics, so audit R1-2 part 2 relocated it to ``butler.core.interrupt``.
``butler.tools.terminal_impl`` and historical test imports still resolve
through this module — keep this file as a one-line re-export rather than
breaking every call site.
"""

from butler.core.interrupt import (  # noqa: F401
    clear_interrupt,
    is_interrupted,
    set_interrupt,
)
