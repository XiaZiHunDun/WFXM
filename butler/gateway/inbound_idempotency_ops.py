"""Butler Inbound Idempotency Ops (Deprecated).

This module is deprecated. Use butler.resilience.inbound_idempotency_ops instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.gateway.inbound_idempotency_ops is deprecated, use butler.resilience.inbound_idempotency_ops instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.resilience.inbound_idempotency_ops import *
try:
    from butler.resilience.inbound_idempotency_ops import __all__
except ImportError:
    pass
