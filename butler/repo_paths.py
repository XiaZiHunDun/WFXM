"""Butler Repo Paths (Deprecated).

This module is deprecated. Use butler.utilities.repo_paths instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.repo_paths is deprecated, use butler.utilities.repo_paths instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.utilities.repo_paths import *
try:
    from butler.utilities.repo_paths import __all__
except ImportError:
    pass