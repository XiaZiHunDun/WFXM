"""Butler Gateway Settings Ops (Deprecated).

This module is deprecated. Use butler.configuration.gateway_ops instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.gateway_settings_ops is deprecated, use butler.configuration.gateway_ops instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.configuration.gateway_ops import *
try:
    from butler.configuration.gateway_ops import __all__
except ImportError:
    pass
