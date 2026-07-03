#!/usr/bin/env python3
"""Append P0-A / P1-C gate budget entries from JSON input.

Usage:
  python scripts/p0a-append-gate-entries.py entries.json
  python scripts/p0a-append-gate-entries.py --stdin <<'EOF'
  [{"main": "butler/foo.py", "ops": "butler/foo_ops.py", "except_budget": 0, "line_budget": 30}]
  EOF
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P0A = ROOT / "tests/test_p0a_exception_governance.py"
P1C = ROOT / "tests/test_p1c_module_split.py"


def _load_entries(path: Path | None, use_stdin: bool) -> list[dict]:
    if use_stdin:
        raw = sys.stdin.read()
    elif path is not None:
        raw = path.read_text(encoding="utf-8")
    else:
        raise SystemExit("Provide entries file or --stdin")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise SystemExit("JSON root must be a list")
    return data


def _existing_keys(text: str) -> set[str]:
    return set(re.findall(r'"((?:butler/)?[^"]+\.py)":\s*\d+', text))


def _insert_before_closing(text: str, marker: str, new_lines: list[str]) -> str:
    idx = text.rfind(marker)
    if idx < 0:
        raise SystemExit(f"marker not found: {marker!r}")
    before = text[:idx].rstrip()
    after = text[idx:]
    block = "\n".join(new_lines)
    if not before.endswith("{"):
        block = "\n" + block
    return before + block + "\n" + after


def main() -> None:
    parser = argparse.ArgumentParser(description="Append P0-A/P1-C gate entries")
    parser.add_argument("entries", nargs="?", type=Path, help="JSON file with module pairs")
    parser.add_argument("--stdin", action="store_true", help="Read JSON from stdin")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    entries = _load_entries(args.entries, args.stdin)
    p0a_text = P0A.read_text(encoding="utf-8")
    p1c_text = P1C.read_text(encoding="utf-8")
    p0a_keys = _existing_keys(p0a_text)
    p1c_keys = _existing_keys(p1c_text)

    p0a_lines: list[str] = []
    p1c_lines: list[str] = []
    for item in entries:
        main = str(item["main"]).replace("\\", "/")
        ops = str(item["ops"]).replace("\\", "/")
        main_budget = int(item.get("except_budget_main", item.get("main_except", 0)))
        ops_budget = int(item.get("except_budget_ops", item.get("ops_except", item.get("except_budget", 0))))
        line_budget = int(item["line_budget"])

        for path, budget in ((main, main_budget), (ops, ops_budget)):
            if path in p0a_keys:
                print(f"skip (exists): {path}", file=sys.stderr)
                continue
            p0a_lines.append(f'    "{path}": {budget},')
            p0a_keys.add(path)

        if ops in p1c_keys:
            print(f"skip p1c (exists): {ops}", file=sys.stderr)
        else:
            p1c_lines.append(f'    "{ops}": {line_budget},')
            p1c_keys.add(ops)

    if not p0a_lines and not p1c_lines:
        print("Nothing to append.")
        return

    if args.dry_run:
        print("P0-A:")
        print("\n".join(p0a_lines))
        print("P1-C:")
        print("\n".join(p1c_lines))
        return

    if p0a_lines:
        p0a_text = _insert_before_closing(p0a_text, "\n}\n\n_EXCEPT_RE", p0a_lines)
        P0A.write_text(p0a_text, encoding="utf-8")
    if p1c_lines:
        p1c_text = _insert_before_closing(p1c_text, "\n}\n\n_PROCESS_TOOL_CALLS", p1c_lines)
        P1C.write_text(p1c_text, encoding="utf-8")

    print(f"Appended {len(p0a_lines)} P0-A and {len(p1c_lines)} P1-C entries.")


if __name__ == "__main__":
    main()
