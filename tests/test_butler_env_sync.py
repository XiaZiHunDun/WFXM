"""Audit 5.1.10: keep .env.example and docs/config/reference.md in sync with
the `BUTLER_*` env vars actually read by the codebase.

The audit found 44+ `BUTLER_` env vars used in code but not documented in
either `.env.example` (operational config) or `docs/config/reference.md`
(developer reference). This drift creates a false sense of safety — code
honors a switch the operator never knew existed.

Whitelist: a small set of names are dynamic or test-only and should not
be considered documentation gaps:

  * ``BUTLER_NONEXISTENT_KEY_*``  — test fixtures (must-NOT-set keys)
  * ``BUTLER_SMOKE_*``            — smoke test marker prefix
  * ``BUTLER_HOOK_*``             — Claude Code hook event payloads, not env vars
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
REFERENCE_MD = REPO_ROOT / "docs" / "config" / "reference.md"
CODE_ROOTS = [REPO_ROOT / "butler", REPO_ROOT / "tests"]

_VAR_RE = re.compile(r"\bBUTLER_[A-Z][A-Z0-9_]+")
_WHITELIST = (
    re.compile(r"^BUTLER_NONEXISTENT_KEY"),
    re.compile(r"^BUTLER_SMOKE_"),
    re.compile(r"^BUTLER_HOOK_"),
    re.compile(r"^BUTLER_MODEL$"),
)


def _whitelisted(name: str) -> bool:
    return any(p.match(name) for p in _WHITELIST)


def _vars_in(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {m.group(0) for m in _VAR_RE.finditer(path.read_text(encoding="utf-8"))}


def _vars_in_code() -> set[str]:
    found: set[str] = set()
    for root in CODE_ROOTS:
        for path in root.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for m in _VAR_RE.finditer(text):
                found.add(m.group(0))
    return {v for v in found if not _whitelisted(v)}


@pytest.mark.unit
def test_butler_env_example_in_sync():
    """Every BUTLER_ env var read in code must appear in .env.example."""
    code_vars = _vars_in_code()
    doc_vars = _vars_in(ENV_EXAMPLE)
    missing = sorted(code_vars - doc_vars)
    assert not missing, (
        f"{len(missing)} BUTLER_ env vars are used in code but missing from "
        f".env.example:\n  " + "\n  ".join(missing)
    )


@pytest.mark.unit
def test_butler_reference_md_in_sync():
    """Every BUTLER_ env var read in code must appear in docs/config/reference.md."""
    code_vars = _vars_in_code()
    doc_vars = _vars_in(REFERENCE_MD)
    missing = sorted(code_vars - doc_vars)
    assert not missing, (
        f"{len(missing)} BUTLER_ env vars are used in code but missing from "
        f"docs/config/reference.md:\n  " + "\n  ".join(missing)
    )
