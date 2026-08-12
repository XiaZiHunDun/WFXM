"""Butler Message Queue (Deprecated).

This module is deprecated. Use butler.resilience.message_queue instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.gateway.message_queue is deprecated, use butler.resilience.message_queue instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.resilience.message_queue import *
try:
    from butler.resilience.message_queue import __all__
except ImportError:
    pass
