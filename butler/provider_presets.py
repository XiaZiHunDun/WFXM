"""Butler Provider Presets (Deprecated).

This module is deprecated. Use butler.configuration.provider_presets instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.provider_presets is deprecated, use butler.configuration.provider_presets instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.configuration.provider_presets import *
try:
    from butler.configuration.provider_presets import __all__
except ImportError:
    pass
