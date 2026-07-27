"""Butler Config Secrets (Deprecated).

This module is deprecated. Use butler.configuration.secrets instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.config_secrets is deprecated, use butler.configuration.secrets instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.configuration.secrets import *
try:
    from butler.configuration.secrets import __all__
except ImportError:
    pass