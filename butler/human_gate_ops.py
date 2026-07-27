"""Butler Human Gate Ops (Deprecated).

This module is deprecated. Use butler.permissions.human_gate_ops instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.human_gate_ops is deprecated, use butler.permissions.human_gate_ops instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.permissions.human_gate_ops import *
try:
    from butler.permissions.human_gate_ops import __all__
except ImportError:
    pass