"""SWE-bench lite verify best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def verify_swebench_instance_safe(inst: Any, ws: Path) -> tuple[bool, str | None]:
    try:
        return bool(inst.verify(ws)), None
    except Exception as exc:
        return False, str(exc)
