#!/usr/bin/env bash
# P3-J: env key audit — code readers vs reference vs .env.example.
# Default: report-only (exit 0). P3J_AUDIT_STRICT=1: fail on undoc code keys.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export P3J_AUDIT_STRICT="${P3J_AUDIT_STRICT:-0}"

python3 - <<'PY'
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

STRICT = os.environ.get("P3J_AUDIT_STRICT", "0").strip() in ("1", "true", "yes", "on")

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


def ref_covers(key: str) -> bool:
    if key in ref_exact:
        return True
    return any(key.startswith(p) for p in ref_prefixes)


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
    "BUTLER_HOOK_EVENT",
    "BUTLER_HOOK_INPUT",
    "BUTLER_HOOK_TOOL",
    "BUTLER_NOTIFY_URLS",
    "BUTLER_RUNTIME_RUN_CONSISTENCY",
    "BUTLER_RUNTIME_SMOKE_PUSH",
    "BUTLER_RUN_REAL_API_SMOKE",
    "BUTLER_WORKFLOW_HANDOFF_ONLY",
    "BUTLER_DISABLE_EXPERIMENTAL_CACHE",
})


def audit_whitelisted(key: str) -> bool:
    if key in IGNORE_EXACT:
        return True
    if key.endswith("_"):
        return True
    return any(p.match(key) for p in WHITELIST)


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

rg = subprocess.run(
    ["rg", "-o", r"BUTLER_[A-Z0-9_]+", "butler/", "scripts/"],
    capture_output=True,
    text=True,
    cwd=Path("."),
)
code_keys = sorted(
    {
        m.group(0)
        for line in rg.stdout.splitlines()
        for m in [re.search(r"BUTLER_[A-Z0-9_]+", line)]
        if m
    }
)

undoc_code = []
for k in code_keys:
    if audit_whitelisted(k):
        continue
    if not ref_covers(k):
        undoc_code.append(k)
undoc_code.sort()

ref_no_code = sorted(
    k
    for k in ref_exact
    if k not in IGNORE_EXACT
    and subprocess.run(
        ["rg", "-qF", k, "butler/", "scripts/"],
        capture_output=True,
    ).returncode
    != 0
)
example_missing = sorted(k for k in ref_exact if k not in env_keys and k not in IGNORE_EXACT)

print("=== P3-J env audit ===")
print(f"reference_exact_keys={len(ref_exact)}")
print(f"reference_prefixes={len(ref_prefixes)}")
print(f"env_example_keys={len(env_keys)}")
print(f"code_butler_script_keys={len(code_keys)}")
print(f"strict={STRICT}")
print("")
print("(a) Code-read BUTLER_* not covered by reference.md:")
if undoc_code:
    for k in undoc_code:
        print(f"  {k}")
else:
    print("  (none)")
print("")
print("(b) Reference table keys with no butler/ or scripts/ occurrence (info):")
if ref_no_code:
    for k in ref_no_code[:40]:
        print(f"  {k}")
    if len(ref_no_code) > 40:
        print(f"  ... +{len(ref_no_code) - 40} more")
else:
    print("  (none)")
print("")
print("(c) Reference keys missing from .env.example (info):")
if example_missing:
    for k in example_missing[:40]:
        print(f"  {k}")
    if len(example_missing) > 40:
        print(f"  ... +{len(example_missing) - 40} more")
else:
    print("  (none)")

if STRICT and undoc_code:
    raise SystemExit(1)
PY

echo "p3j-env-audit: OK"
