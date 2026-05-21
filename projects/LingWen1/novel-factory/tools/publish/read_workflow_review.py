#!/usr/bin/env python3
"""Print review_queue pending count from workflow_state.json (for publish preflight)."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def pending_count(state_path: Path) -> tuple[int, int, int]:
    data = json.loads(state_path.read_text(encoding="utf-8"))
    rq = data.get("review_queue") or {}
    if not isinstance(rq, dict):
        return 0, 0, 0
    pending = rq.get("pending") or []
    in_review = rq.get("in_review") or []
    if not isinstance(pending, list):
        pending = []
    if not isinstance(in_review, list):
        in_review = []
    return len(pending), len(in_review), len(pending) + len(in_review)


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    wf = root / "workflow_state.json"
    if not wf.is_file():
        print("MISSING")
        return 2
    p, r, total = pending_count(wf)
    print(f"{p} {r} {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
