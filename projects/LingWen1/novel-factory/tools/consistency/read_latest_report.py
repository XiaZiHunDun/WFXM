#!/usr/bin/env python3
"""Read P0/P1 from the newest consistency_check_*.json (for publish preflight)."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def find_latest_report(report_dir: Path) -> Path | None:
    if not report_dir.is_dir():
        return None
    candidates = sorted(
        report_dir.glob("consistency_check_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def load_severity(report_path: Path) -> dict[str, int]:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    by = data.get("by_severity") or {}
    if not isinstance(by, dict):
        by = {}
    return {
        "P0": int(by.get("P0", 0) or 0),
        "P1": int(by.get("P1", 0) or 0),
        "P2": int(by.get("P2", 0) or 0),
        "total_issues": int(data.get("total_issues", 0) or 0),
    }


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    report_dir = root / "06_意见仓库" / "07_一致性检查"
    latest = find_latest_report(report_dir)
    if latest is None:
        print("MISSING")
        return 2
    sev = load_severity(latest)
    # line: P0 P1 P2 total relpath
    try:
        rel = latest.relative_to(root.resolve())
    except ValueError:
        rel = Path(latest.name)
    print(
        f"{sev['P0']} {sev['P1']} {sev['P2']} {sev['total_issues']} {rel.as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
