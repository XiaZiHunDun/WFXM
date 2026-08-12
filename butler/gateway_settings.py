"""Butler Gateway Settings (Deprecated).

This module is deprecated. Use butler.configuration.gateway instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.gateway_settings is deprecated, use butler.configuration.gateway instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.configuration.gateway import *
try:
    from butler.configuration.gateway import __all__
except ImportError:
    pass
