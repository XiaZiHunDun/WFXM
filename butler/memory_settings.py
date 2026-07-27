"""Butler Memory Settings (Deprecated).

This module is deprecated. Use butler.configuration.memory instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.memory_settings is deprecated, use butler.configuration.memory instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.configuration.memory import *
try:
    from butler.configuration.memory import __all__
except ImportError:
    pass