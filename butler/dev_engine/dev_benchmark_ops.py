"""Dev benchmark run best-effort helpers (P0-A)."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


def run_swebench_instance_safe(
    inst: Any,
    inst_dir: Path,
) -> tuple[bool, str | None]:
    try:
        inst.setup_workspace(inst_dir)
        inst.apply_oracle(inst_dir)
        if inst.verify(inst_dir):
            return True, None
        return False, f"{inst.instance_id}: verify failed after oracle patch"
    except Exception as exc:
        return False, f"{inst.instance_id}: {exc}"


def run_benchmark_fn_safe(
    bench_fn: Callable[..., Any],
    tmp: Path,
    collector: Any,
) -> tuple[Any | None, str | None]:
    t0 = time.time()
    try:
        result = bench_fn(tmp, collector)
        result.elapsed_seconds = time.time() - t0
        return result, None
    except Exception as exc:
        return None, str(exc)
