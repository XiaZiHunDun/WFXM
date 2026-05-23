#!/usr/bin/env python3
"""Append a脱敏 production utterance to production_utterance_catalog.yaml.

Usage:
  python3 scripts/corpus/append_production.py --user "帮我看下 README" \\
    --kind llm --script read_readme --expect-json '{"response_contains_any":["README"]}'

  python3 scripts/corpus/append_production.py --from-yaml new_entry.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.corpus.harness.gateway_ops import next_production_id  # noqa: E402

PROD_PATH = (
    ROOT
    / "tests/corpus/suites/wechat_real/lw_real/production_utterance_catalog.yaml"
)


def _load_doc() -> dict[str, Any]:
    return yaml.safe_load(PROD_PATH.read_text(encoding="utf-8")) or {}


def _save_doc(doc: dict[str, Any]) -> None:
    rows = doc.get("utterance_catalog") or []
    doc["meta"] = {
        **(doc.get("meta") or {}),
        "entry_count": len(rows),
        "last_append": rows[-1]["id"] if rows else None,
    }
    PROD_PATH.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def build_entry(args: argparse.Namespace) -> dict[str, Any]:
    if args.from_yaml:
        path = Path(args.from_yaml)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            entry = data[0]
        else:
            entry = data
        if not isinstance(entry, dict):
            raise SystemExit("from-yaml must be a dict or single-item list")
        return entry

    if not args.user:
        raise SystemExit("--user is required unless --from-yaml is set")

    entry: dict[str, Any] = {
        "user": args.user.strip(),
        "category": args.category or "production_real",
        "fixture": args.fixture or "lingwen",
        "kind": args.kind or "llm",
        "tier": "production",
        "quality": "strict",
        "runner": "production",
        "source_file": args.source or f"production/脱敏{date_tag()}",
    }
    if args.script:
        entry["script"] = args.script
    if args.setup:
        entry["setup"] = args.setup
    if args.expect_json:
        entry["expect"] = json.loads(args.expect_json)
    return entry


def date_tag() -> str:
    from datetime import date

    return date.today().strftime("%Y%m%d")


def append(entry: dict[str, Any], *, dry_run: bool = False) -> str:
    doc = _load_doc()
    rows = list(doc.get("utterance_catalog") or [])
    if not entry.get("id"):
        entry["id"] = next_production_id()
    if any(r.get("id") == entry["id"] for r in rows):
        raise SystemExit(f"duplicate id: {entry['id']}")

    if dry_run:
        print(yaml.safe_dump(entry, allow_unicode=True, sort_keys=False))
        return str(entry["id"])

    rows.append(entry)
    doc["utterance_catalog"] = rows
    _save_doc(doc)
    print(f"Appended {entry['id']} → {PROD_PATH.relative_to(ROOT)}")
    return str(entry["id"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Append production corpus entry")
    parser.add_argument("--user", help="脱敏后的用户原话")
    parser.add_argument("--kind", choices=["command", "detail", "llm"], default="llm")
    parser.add_argument("--script", help="mock script name for llm kind")
    parser.add_argument("--fixture", default="lingwen")
    parser.add_argument("--category", default="production_real")
    parser.add_argument("--setup", help="optional setup key")
    parser.add_argument("--source", help="source_file trace")
    parser.add_argument("--expect-json", help="JSON object for expect block")
    parser.add_argument("--from-yaml", help="load full entry from yaml file")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    entry = build_entry(args)
    append(entry, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
