"""Butler Human Gate (Deprecated).

This module is deprecated. Use butler.permissions.human_gate instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.human_gate is deprecated, use butler.permissions.human_gate instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.permissions.human_gate import *
try:
    from butler.permissions.human_gate import __all__
except ImportError:
    pass
