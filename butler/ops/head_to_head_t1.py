"""Head-to-head T1 — re-export from butler.ops.head_to_head."""

from typing import Any

from butler.ops.head_to_head import T1, run_head_to_head_t1
from butler.ops.head_to_head_common import reset_workspace as _reset


FIXTURE = T1.fixture
WORKSPACE = T1.fixture / "ws"


def reset_workspace() -> None:
    _reset(T1)


run_butler_delegate = lambda **kw: __import__(
    "butler.ops.head_to_head_common", fromlist=["run_butler"]
).run_butler(T1, **kw)
run_cc_cli = lambda **kw: __import__(
    "butler.ops.head_to_head_common", fromlist=["run_cc"]
).run_cc(T1, **kw)

__all__ = [
    "FIXTURE",
    "WORKSPACE",
    "reset_workspace",
    "run_butler_delegate",
    "run_cc_cli",
    "run_head_to_head_t1",
]
