"""Oracle gold few-shot patterns for B9 LIVE delegate (read → patch → pytest)."""

from __future__ import annotations

import os

from butler.env_parse import env_truthy

# Curated from passing oracle_apply paths — pattern only, not task-specific files.
B9_ORACLE_FEWSHOT_CASES: tuple[dict[str, str], ...] = (
    {
        "title": "logic bug (wrong operator)",
        "steps": "read_file test_b9.py → read_file calc.py → patch calc.py → pytest",
        "patch_hint": "old: `return a + b`  new: `return a * b`  (match test expectation)",
    },
    {
        "title": "import mismatch (module name vs file)",
        "steps": "list_directory → read_file main.py → patch import line → pytest",
        "patch_hint": "file is helpers.py but import says helper → change to `from helpers import ...`",
    },
    {
        "title": "wrong return literal",
        "steps": "read_file test_b9.py → read_file greet.py → patch return only → pytest",
        "patch_hint": "test expects 'hello' but code returns 'hi' → fix greet.py return literal",
    },
    {
        "title": "single-file threshold/config fix",
        "steps": "read_file test_b9.py → read_file config.py → patch constant → pytest",
        "patch_hint": "adjust THRESHOLD (or similar) so predicate in test passes; do not edit test_b9.py",
    },
    {
        "title": "add missing function/method (test-driven)",
        "steps": "read_file test_b9.py → read_file source → write_file or patch to add function → pytest",
        "patch_hint": "implement the function/method the test calls; match return type and literals exactly",
    },
    {
        "title": "off-by-one / loop bound",
        "steps": "read_file test_b9.py → read_file loops module → patch range bound → pytest",
        "patch_hint": "if sum 0..n-1 expected, use range(n) not range(n+1)",
    },
)


def b9_oracle_fewshot_enabled() -> bool:
    return env_truthy("BUTLER_B9_ORACLE_FEWSHOT", default=True)


def format_b9_oracle_fewshot_block(*, max_cases: int = 2) -> str:
    if not b9_oracle_fewshot_enabled() or max_cases <= 0:
        return ""
    lines = ["<b9-oracle-fewshot>", "## Proven fix patterns (oracle gold)"]
    for case in B9_ORACLE_FEWSHOT_CASES[:max_cases]:
        lines.append(f"### {case['title']}")
        lines.append(f"- steps: {case['steps']}")
        lines.append(f"- patch: {case['patch_hint']}")
    lines.append("</b9-oracle-fewshot>")
    return "\n".join(lines)


__all__ = [
    "B9_ORACLE_FEWSHOT_CASES",
    "b9_oracle_fewshot_enabled",
    "format_b9_oracle_fewshot_block",
]
