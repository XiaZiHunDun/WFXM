"""Backward-compat re-export — implementation in ``butler.delegate.task_kind``."""

from butler.delegate.task_kind import (  # noqa: F401
    infer_delegate_task_kind,
    is_dev_verify_exempt,
)

__all__ = [
    "infer_delegate_task_kind",
    "is_dev_verify_exempt",
]
