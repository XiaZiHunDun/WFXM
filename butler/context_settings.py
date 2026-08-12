"""Butler Context Settings (Deprecated).

This module is deprecated. Use butler.configuration.context instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.context_settings is deprecated, use butler.configuration.context instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.configuration.context import *
try:
    from butler.configuration.context import __all__
except ImportError:
    pass
