"""Extended seed data — comprehensive knowledge for all domains.

This module is deprecated. Use butler.memory.knowledge_warehouse.seed_data instead.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "butler.memory.knowledge_warehouse.seed_data_extended is deprecated. "
    "Use butler.memory.knowledge_warehouse.seed_data instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .seed_data import EXTENDED_MATERIALS