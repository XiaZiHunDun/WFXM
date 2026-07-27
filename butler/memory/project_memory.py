"""Project memory helpers.

Deprecated: Use `butler.memory.project_memory` package instead.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "butler.memory.project_memory module is deprecated, "
    "use butler.memory.project_memory package instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.memory.project_memory.__init__ import (
    MarkdownMemory,
    ProjectFactsStore,
    ProjectMemory,
    filter_memory_hits_by_role,
    looks_correction_memory,
    memory_auto_approve_mode,
    memory_auto_fact_enabled,
    normalize_section_name,
    project_prefetch_max_chars,
    sections_for_agent_role,
)

__all__ = [
    "memory_auto_fact_enabled",
    "memory_auto_approve_mode",
    "looks_correction_memory",
    "sections_for_agent_role",
    "project_prefetch_max_chars",
    "filter_memory_hits_by_role",
    "normalize_section_name",
    "MarkdownMemory",
    "ProjectFactsStore",
    "ProjectMemory",
]