"""Butler Config Ops (Deprecated).

This module is deprecated. Use butler.configuration.settings_ops instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.config_ops is deprecated, use butler.configuration.settings_ops instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.configuration.settings_ops import *
try:
    from butler.configuration.settings_ops import __all__
except ImportError:
    pass