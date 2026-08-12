"""Butler Config Secrets Ops (Deprecated).

This module is deprecated. Use butler.configuration.secrets_ops instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.config_secrets_ops is deprecated, use butler.configuration.secrets_ops instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.configuration.secrets_ops import *
try:
    from butler.configuration.secrets_ops import __all__
except ImportError:
    pass
