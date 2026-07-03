"""SWE-bench live verify best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def verify_swe_instance_safe(inst: Any, ws: Path) -> tuple[bool, str]:
    try:
        ok = inst.verify(ws)
    except Exception as exc:
        return False, str(exc)
    return ok, "tests passed" if ok else "tests failed"
