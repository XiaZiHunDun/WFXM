"""Butler-level (global) memory: owner profile and cross-project experience.

Deprecated: Use `butler.memory.butler_memory` package instead.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "butler.memory.butler_memory module is deprecated, "
    "use butler.memory.butler_memory package instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.memory.butler_memory.__init__ import (
    ButlerMemory,
    ExperienceStore,
    ProfileStore,
    _reject_injection,
)

__all__ = [
    "ButlerMemory",
    "ExperienceStore",
    "ProfileStore",
    "_reject_injection",
]
