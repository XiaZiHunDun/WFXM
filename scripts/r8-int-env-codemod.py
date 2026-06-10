#!/usr/bin/env python3
"""One-shot codemod: replace int(os.getenv(...)) with int_env(...) in butler/."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "butler"
SKIP = {"env_parse.py"}

# max(N, int(os.getenv("VAR", "D"))) -> int_env("VAR", D, min=N)
PAT_MAX = re.compile(
    r"max\(\s*(\d+)\s*,\s*int\(\s*os\.getenv\(\s*"
    r'"([A-Z][A-Z0-9_]*)"\s*,\s*"([^"]*)"\s*\)\s*\)\s*\)'
)

# max(N, int(os.getenv("VAR", str(x)))) — keep manual

# int(os.getenv("VAR", "NUM")) -> int_env("VAR", NUM)
PAT_SIMPLE = re.compile(
    r'int\(\s*os\.getenv\(\s*"([A-Z][A-Z0-9_]*)"\s*,\s*"([^"]*)"\s*\)\s*\)'
)

# int(os.getenv("VAR", "") or "NUM") -> int_env("VAR", NUM)
PAT_OR = re.compile(
    r'int\(\s*os\.getenv\(\s*"([A-Z][A-Z0-9_]*)"\s*,\s*""\s*\)\s*or\s*"([^"]*)"\s*\)'
)

# max(N, min(M, int(os.getenv("VAR", "D")))) -> int_env("VAR", D, min=N, max=M)
PAT_MINMAX = re.compile(
    r"max\(\s*(\d+)\s*,\s*min\(\s*(\d+)\s*,\s*int\(\s*os\.getenv\(\s*"
    r'"([A-Z][A-Z0-9_]*)"\s*,\s*"([^"]*)"\s*\)\s*\)\s*\)\s*\)'
)


def _ensure_import(text: str) -> str:
    if "from butler.env_parse import" in text:
        if "int_env" in text.split("from butler.env_parse import", 1)[1].split("\n", 1)[0]:
            return text
        text = re.sub(
            r"(from butler\.env_parse import [^\n]+)",
            lambda m: m.group(1).rstrip() + ", int_env",
            text,
            count=1,
        )
        return text
    anchor = "from __future__ import annotations\n\n"
    if anchor in text:
        return text.replace(
            anchor,
            anchor + "from butler.env_parse import int_env\n",
            1,
        )
    return "from butler.env_parse import int_env\n\n" + text


def _transform(content: str) -> tuple[str, int]:
    n = 0

    def _minmax(m: re.Match[str]) -> str:
        nonlocal n
        n += 1
        lo, hi, var, default = m.group(1), m.group(2), m.group(3), m.group(4)
        return f'int_env("{var}", {default}, min={lo}, max={hi})'

    content = PAT_MINMAX.sub(_minmax, content)

    def _max(m: re.Match[str]) -> str:
        nonlocal n
        n += 1
        lo, var, default = m.group(1), m.group(2), m.group(3)
        return f'int_env("{var}", {default}, min={lo})'

    content = PAT_MAX.sub(_max, content)

    def _or(m: re.Match[str]) -> str:
        nonlocal n
        n += 1
        var, default = m.group(1), m.group(2)
        return f'int_env("{var}", {default})'

    content = PAT_OR.sub(_or, content)

    def _simple(m: re.Match[str]) -> str:
        nonlocal n
        n += 1
        var, default = m.group(1), m.group(2)
        return f'int_env("{var}", {default})'

    content = PAT_SIMPLE.sub(_simple, content)
    if n:
        content = _ensure_import(content)
    return content, n


def main() -> None:
    total = 0
    for path in sorted(ROOT.rglob("*.py")):
        if path.name in SKIP:
            continue
        original = path.read_text(encoding="utf-8")
        updated, n = _transform(original)
        if n:
            path.write_text(updated, encoding="utf-8")
            print(f"{path.relative_to(ROOT.parent)}: {n}")
            total += n
    print(f"total replacements: {total}")


if __name__ == "__main__":
    main()
