"""Butler Env Parse (Deprecated).

This module is deprecated. Use butler.utilities.env_parse instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.env_parse is deprecated, use butler.utilities.env_parse instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.utilities.env_parse import *
try:
    from butler.utilities.env_parse import __all__
except ImportError:
    pass
