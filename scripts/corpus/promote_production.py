#!/usr/bin/env python3
"""Promote a production utterance entry into reference_utterance_strict.yaml.

Usage:
  python3 scripts/corpus/promote_production.py PROD-001
  python3 scripts/corpus/promote_production.py PROD-001 --dry-run
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROD_PATH = (
    ROOT
    / "tests/corpus/suites/wechat_real/lw_real/production_utterance_catalog.yaml"
)
STRICT_PATH = (
    ROOT
    / "tests/corpus/suites/wechat_real/lw_real/reference_utterance_strict.yaml"
)


def _load_catalog(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = data.get("utterance_catalog") or []
    if not isinstance(rows, list):
        raise SystemExit(f"{path}: utterance_catalog must be a list")
    return data


def promote(prod_id: str, *, dry_run: bool = False) -> None:
    prod_doc = _load_catalog(PROD_PATH)
    strict_doc = _load_catalog(STRICT_PATH)
    prod_rows = prod_doc["utterance_catalog"]
    strict_rows = strict_doc["utterance_catalog"]

    source = next((r for r in prod_rows if r.get("id") == prod_id), None)
    if not source:
        raise SystemExit(f"unknown production id: {prod_id}")

    new_id = prod_id.replace("PROD-", "REF-PROMO-", 1)
    if any(r.get("id") == new_id for r in strict_rows):
        raise SystemExit(f"already promoted: {new_id}")

    promoted = copy.deepcopy(source)
    promoted["id"] = new_id
    promoted["tier"] = "reference"
    promoted["quality"] = "strict"
    promoted.pop("runner", None)
    promoted["source_file"] = f"promoted-from:{prod_id}"
    promoted["promoted_from"] = prod_id

    if dry_run:
        print(yaml.safe_dump(promoted, allow_unicode=True, sort_keys=False))
        return

    strict_rows.append(promoted)
    strict_doc["utterance_catalog"] = strict_rows
    meta = strict_doc.setdefault("meta", {})
    meta["entry_count"] = len(strict_rows)
    meta["last_promotion"] = new_id

    STRICT_PATH.write_text(
        yaml.safe_dump(strict_doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    # Record promotion trace on production row (optional audit)
    for row in prod_rows:
        if row.get("id") == prod_id:
            hist = list(row.get("promotion_history") or [])
            hist.append({"to": new_id, "tier": "reference_strict"})
            row["promotion_history"] = hist
            break
    prod_doc["utterance_catalog"] = prod_rows
    PROD_PATH.write_text(
        yaml.safe_dump(prod_doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Promoted {prod_id} → {new_id} in {STRICT_PATH.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote production corpus to strict tier")
    parser.add_argument("prod_id", help="e.g. PROD-001")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    promote(args.prod_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
