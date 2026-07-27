"""Butler Inbound Idempotency (Deprecated).

This module is deprecated. Use butler.resilience.inbound_idempotency instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.gateway.inbound_idempotency is deprecated, use butler.resilience.inbound_idempotency instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.resilience.inbound_idempotency import *
try:
    from butler.resilience.inbound_idempotency import __all__
except ImportError:
    pass