#!/usr/bin/env python3
"""P3-J: diff static BUTLER_* stubs from code vs reference.md (report-only by default)."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WHITELIST = (
    re.compile(r"^BUTLER_NONEXISTENT_KEY"),
    re.compile(r"^BUTLER_SMOKE_"),
    re.compile(r"^BUTLER_HOOK_"),
    re.compile(r"^BUTLER_TEST_"),
    re.compile(r"^BUTLER_WECHAT_.*_SIM$"),
    re.compile(r"^BUTLER_MODEL$"),
)

IGNORE_EXACT = frozenset({
    "BUTLER_PY",
    "BUTLER_PYTHON",
    "BUTLER_NAME",
    "BUTLER_ONLY",
    "BUTLER_BLOCKED_PROJECT_TOOLS",
    "BUTLER_FOO",
})


def _reference_keys() -> tuple[set[str], list[str]]:
    text = (ROOT / "docs/config/reference.md").read_text(encoding="utf-8")
    exact: set[str] = set()
    prefixes: list[str] = []
    for line in text.splitlines():
        if not re.match(r"\s*\| `BUTLER_", line):
            continue
        for tok in re.findall(r"BUTLER_[A-Z0-9_*]+", line):
            if tok.endswith("*"):
                prefixes.append(tok[:-1])
            else:
                exact.add(tok)
    return exact, prefixes


def _code_keys() -> set[str]:
    proc = subprocess.run(
        ["rg", "-o", r"BUTLER_[A-Z0-9_]+", "butler/", "scripts/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    out: set[str] = set()
    for line in proc.stdout.splitlines():
        m = re.search(r"BUTLER_[A-Z0-9_]+", line)
        if m:
            out.add(m.group(0))
    return out


def _ignored(key: str) -> bool:
    if key in IGNORE_EXACT or key.endswith("_"):
        return True
    return any(p.match(key) for p in WHITELIST)


def main() -> int:
    strict = os.environ.get("P3J_SCHEMA_STRICT", "0").strip() in ("1", "true", "yes", "on")
    exact, prefixes = _reference_keys()
    code = _code_keys()

    def covered(key: str) -> bool:
        if key in exact:
            return True
        return any(key.startswith(p) for p in prefixes)

    stub_only = sorted(k for k in code if not _ignored(k) and not covered(k))
    print("=== P3-J env schema PoC ===")
    print(f"code_keys={len(code)} reference_exact={len(exact)} strict={strict}")
    print("stub_not_in_reference (first 40):")
    if stub_only:
        for k in stub_only[:40]:
            print(f"  {k}")
        if len(stub_only) > 40:
            print(f"  ... +{len(stub_only) - 40} more")
    else:
        print("  (none)")
    return 1 if strict and stub_only else 0


if __name__ == "__main__":
    sys.exit(main())
