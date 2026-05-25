"""Append-only registry audit log."""

from __future__ import annotations

from datetime import datetime, timezone

from butler.registry.paths import audit_path


def append_audit(event: str, target: str, detail: str = "") -> None:
    path = audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    line = f"{ts}\t{event}\t{target}\t{detail}\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)
