"""Butler Tenant (Deprecated).

This module is deprecated. Use butler.utilities.tenant instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.tenant is deprecated, use butler.utilities.tenant instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.utilities.tenant import *
try:
    from butler.utilities.tenant import __all__
except ImportError:
    pass
