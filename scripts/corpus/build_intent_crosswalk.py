#!/usr/bin/env python3
"""Regenerate tests/corpus/intent_crosswalk.yaml from live corpora."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.corpus.harness.corpus_intent import build_crosswalk, validate_crosswalk  # noqa: E402

OUT = ROOT / "tests/corpus/intent_crosswalk.yaml"


def main() -> None:
    doc = build_crosswalk()
    errors = validate_crosswalk(doc)
    if errors:
        print("WARN: built crosswalk has validation issues:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)

    OUT.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(doc.get('cross_refs') or [])} intents → {OUT.relative_to(ROOT)}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
