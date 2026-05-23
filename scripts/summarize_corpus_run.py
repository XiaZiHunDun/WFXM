#!/usr/bin/env python3
"""Summarize tests/corpus/archive/runs/*.jsonl for issue-map drafting."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

_RUNS = Path(__file__).resolve().parents[1] / "tests" / "corpus" / "archive" / "runs"


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if path is None:
        files = sorted(_RUNS.glob("*.jsonl"))
        if not files:
            print("no jsonl under", _RUNS, file=sys.stderr)
            return 1
        path = files[-1]
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        print("empty", path)
        return 1
    run_id = rows[0].get("run_id", "?")
    by_status = Counter(r["status"] for r in rows)
    by_fail = Counter(r["fail_type"] for r in rows if r.get("fail_type"))
    by_dim_fail = Counter(
        (r.get("dimension", ""), r.get("fail_type", "")) for r in rows if r["status"] == "failed"
    )
    print(f"run_id: {run_id}")
    print(f"file: {path}")
    print(f"rows: {len(rows)}")
    print("status:", dict(by_status))
    if by_fail:
        print("fail_type:", dict(by_fail))
    if by_dim_fail:
        print("dimension×fail_type (failed only):")
        for (dim, ft), n in sorted(by_dim_fail.items()):
            print(f"  {dim} / {ft}: {n}")
    failed_ids = [r["case_id"] for r in rows if r["status"] == "failed"]
    if failed_ids:
        print("failed case_ids:", ", ".join(failed_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
