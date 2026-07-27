"""Butler Human Gate (Deprecated).

This module is deprecated. Use butler.permissions.human_gate instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.human_gate is deprecated, use butler.permissions.human_gate instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.permissions.human_gate import *
from butler.permissions.human_gate import _workflow_auto_resume_enabled, _save_pending, _auto_resume_workflow, _is_gate_expired
try:
    from butler.permissions.human_gate import __all__
except ImportError:
    pass