"""Butler Logging Config (Deprecated).

This module is deprecated. Use butler.utilities.logging_config instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.logging_config is deprecated, use butler.utilities.logging_config instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.utilities.logging_config import *
try:
    from butler.utilities.logging_config import __all__
except ImportError:
    pass
