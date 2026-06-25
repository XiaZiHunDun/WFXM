#!/usr/bin/env bash
# Compare reference.md table keys vs .env.example (ignores prose/callout-only names).
set -euo pipefail
cd "$(dirname "$0")/.."

python3 - <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

ref_text = Path("docs/config/reference.md").read_text(encoding="utf-8")
env_lines = Path(".env.example").read_text(encoding="utf-8").splitlines()

ref_exact: set[str] = set()
ref_prefixes: list[str] = []
for line in ref_text.splitlines():
    if not re.match(r"\s*\| `BUTLER_", line):
        continue
    for tok in re.findall(r"BUTLER_[A-Z0-9_*]+", line):
        if tok.endswith("*"):
            ref_prefixes.append(tok[:-1])
        else:
            ref_exact.add(tok)

env_keys: set[str] = set()
for line in env_lines:
    stripped = line.strip()
    if not stripped.startswith("#") and not stripped.startswith("BUTLER_"):
        continue
    if stripped.startswith("#") and "=" not in stripped:
        continue
    m = re.search(r"(BUTLER_[A-Z0-9_]+)", stripped)
    if m:
        env_keys.add(m.group(1))


def ref_covers(key: str) -> bool:
    if key in ref_exact:
        return True
    return any(key.startswith(prefix) for prefix in ref_prefixes)


# Prose examples / runtime hook injection (documented outside the main table).
ref_only_ok = {
    "BUTLER_FOO",
    "BUTLER_HOOK_EVENT",
    "BUTLER_HOOK_INPUT",
    "BUTLER_HOOK_TOOL",
}

only_ref = sorted(k for k in ref_exact if k not in env_keys and k not in ref_only_ok)
only_env = sorted(k for k in env_keys if not ref_covers(k))

if only_ref or only_env:
    if only_ref:
        print("reference table keys missing from .env.example:")
        for k in only_ref:
            print(f"  {k}")
    if only_env:
        print(".env.example keys missing from reference.md table:")
        for k in only_env:
            print(f"  {k}")
    sys.exit(1)

print(
    f"check-env-reference-sync: OK ({len(ref_exact)} exact + {len(ref_prefixes)} prefix, "
    f"{len(env_keys)} .env.example keys)"
)
PY
