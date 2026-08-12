"""Butler Config (Deprecated).

This module is deprecated. Use butler.configuration.settings instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.config is deprecated, use butler.configuration.settings instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.configuration.settings import *
try:
    from butler.configuration.settings import __all__
except ImportError:
    pass
