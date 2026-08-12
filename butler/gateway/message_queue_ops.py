"""Butler Message Queue Ops (Deprecated).

This module is deprecated. Use butler.resilience.message_queue_ops instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.gateway.message_queue_ops is deprecated, use butler.resilience.message_queue_ops instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.resilience.message_queue_ops import *
try:
    from butler.resilience.message_queue_ops import __all__
except ImportError:
    pass
