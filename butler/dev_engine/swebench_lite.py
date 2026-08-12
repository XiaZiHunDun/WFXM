"""SWE-bench Lite adapted benchmark.

Deprecated: Use `butler.dev_engine.swebench_lite` package instead.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "butler.dev_engine.swebench_lite module is deprecated, "
    "use butler.dev_engine.swebench_lite package instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.dev_engine.swebench_lite import (
    SWEInstance,
    get_all_instances,
    get_instance,
    get_instances_by_category,
    run_oracle_verification,
    _instances,
)

__all__ = [
    "SWEInstance",
    "get_all_instances",
    "get_instance",
    "get_instances_by_category",
    "run_oracle_verification",
    "_instances",
]
