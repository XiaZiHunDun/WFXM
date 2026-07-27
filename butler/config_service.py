"""Butler Config Service (Deprecated).

This module is deprecated. Use butler.configuration.service instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.config_service is deprecated, use butler.configuration.service instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.configuration.service import *
try:
    from butler.configuration.service import __all__
except ImportError:
    pass