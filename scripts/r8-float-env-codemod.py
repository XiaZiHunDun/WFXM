#!/usr/bin/env python3
"""One-shot codemod: replace float(os.getenv(...)) with float_env(...) in butler/."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "butler"
SKIP = {"env_parse.py"}

PAT_MINMAX = re.compile(
    r"max\(\s*(\d+(?:\.\d+)?)\s*,\s*min\(\s*(\d+(?:\.\d+)?)\s*,\s*float\(\s*os\.getenv\(\s*"
    r'"([A-Z][A-Z0-9_]*)"\s*,\s*"([^"]*)"\s*\)\s*\)\s*\)\s*\)'
)
PAT_MAX = re.compile(
    r"max\(\s*(\d+(?:\.\d+)?)\s*,\s*float\(\s*os\.getenv\(\s*"
    r'"([A-Z][A-Z0-9_]*)"\s*,\s*"([^"]*)"\s*\)\s*\)\s*\)'
)
PAT_OR = re.compile(
    r'float\(\s*os\.getenv\(\s*"([A-Z][A-Z0-9_]*)"\s*,\s*""\s*\)\s*or\s*"([^"]*)"\s*\)'
)
PAT_OR_NUM = re.compile(
    r'float\(\s*os\.getenv\(\s*"([A-Z][A-Z0-9_]*)"\s*,\s*"([^"]*)"\s*\)\s*or\s*"([^"]*)"\s*\)'
)
PAT_SIMPLE = re.compile(
    r'float\(\s*os\.getenv\(\s*"([A-Z][A-Z0-9_]*)"\s*,\s*"([^"]*)"\s*\)\s*\)'
)
PAT_MAX_OR_CONST = re.compile(
    r"max\(\s*(\d+(?:\.\d+)?)\s*,\s*float\(\s*os\.getenv\(\s*"
    r'"([A-Z][A-Z0-9_]*)"\s*,\s*""\s*\)\s*or\s*([_A-Z][A-Z0-9_]+)\s*\)\s*\)'
)
PAT_STRIP_OR = re.compile(
    r'float\(\s*os\.getenv\(\s*"([A-Z][A-Z0-9_]*)"\s*,\s*"([^"]*)"\s*\)\.strip\(\)\s*or\s*"([^"]*)"\s*\)'
)


def _ensure_import(text: str) -> str:
    if re.search(r"from butler\.env_parse import[^\n]*\bfloat_env\b", text):
        return text
    if "from butler.env_parse import" in text:
        return re.sub(
            r"(from butler\.env_parse import [^\n]+)",
            lambda m: m.group(1).rstrip() + ", float_env",
            text,
            count=1,
        )
    anchor = "from __future__ import annotations\n\n"
    if anchor in text:
        return text.replace(
            anchor,
            anchor + "from butler.env_parse import float_env\n",
            1,
        )
    return "from butler.env_parse import float_env\n\n" + text


def _transform(content: str) -> tuple[str, int]:
    n = 0

    def bump(m: re.Match[str], repl: str) -> str:
        nonlocal n
        n += 1
        return repl

    content = PAT_MINMAX.sub(
        lambda m: bump(m, f'float_env("{m.group(3)}", {m.group(4)}, min={m.group(1)}, max={m.group(2)})'),
        content,
    )
    content = PAT_MAX.sub(
        lambda m: bump(m, f'float_env("{m.group(2)}", {m.group(3)}, min={m.group(1)})'),
        content,
    )
    content = PAT_MAX_OR_CONST.sub(
        lambda m: bump(m, f'float_env("{m.group(2)}", {m.group(3)}, min={m.group(1)})'),
        content,
    )
    content = PAT_OR.sub(
        lambda m: bump(m, f'float_env("{m.group(1)}", {m.group(2)})'),
        content,
    )
    content = PAT_OR_NUM.sub(
        lambda m: bump(m, f'float_env("{m.group(1)}", {m.group(3)})'),
        content,
    )
    content = PAT_STRIP_OR.sub(
        lambda m: bump(m, f'float_env("{m.group(1)}", {m.group(3)})'),
        content,
    )
    content = PAT_SIMPLE.sub(
        lambda m: bump(m, f'float_env("{m.group(1)}", {m.group(2)})'),
        content,
    )
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
