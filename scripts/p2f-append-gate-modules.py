#!/usr/bin/env python3
"""Append modules to P2-F mypy strict gate and pyproject.toml overrides.

Usage:
  python scripts/p2f-append-gate-modules.py butler/core/foo.py butler/core/bar.py
  python scripts/p2f-append-gate-modules.py --stdin <<'EOF'
  butler/core/foo.py
  butler/core/bar.py
  EOF
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/butler-mypy-strict-gate.sh"
PYPROJECT = ROOT / "pyproject.toml"


def _normalize_path(raw: str) -> str:
    """Accept ``butler/core/foo.py`` or ``butler.core.foo``; return gate file path."""
    p = raw.replace("\\", "/").strip()
    if p.startswith("butler.") and not p.endswith(".py"):
        return p.replace(".", "/") + ".py"
    if p.endswith(".py"):
        return p
    raise ValueError(f"Invalid module path: {raw!r}")


def _module_name(path: str) -> str:
    """Dotted module id for pyproject (e.g. ``butler.core.foo``)."""
    p = _normalize_path(path)
    if p.endswith(".py"):
        p = p[:-3]
    return p.replace("/", ".")


def _existing_gate_modules(text: str) -> set[str]:
    return set(re.findall(r"^\s+(butler/[^\s]+\.py)\s*$", text, re.MULTILINE))


def _existing_pyproject_modules(text: str) -> set[str]:
    block = re.search(
        r'\[\[tool\.mypy\.overrides\]\]\s*\nmodule = \[([^\]]+)\]',
        text,
        re.DOTALL,
    )
    if not block:
        return set()
    return set(re.findall(r'"([^"]+)"', block.group(1)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Append P2-F mypy strict gate modules")
    parser.add_argument("paths", nargs="*", help="Module paths (butler/.../*.py)")
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    paths: list[str] = list(args.paths)
    if args.stdin:
        paths.extend(line.strip() for line in sys.stdin if line.strip())

    if not paths:
        raise SystemExit("No module paths provided")

    gate_text = GATE.read_text(encoding="utf-8")
    py_text = PYPROJECT.read_text(encoding="utf-8")
    gate_existing = _existing_gate_modules(gate_text)
    py_existing = _existing_pyproject_modules(py_text)

    new_gate: list[str] = []
    new_py: list[str] = []
    for raw in paths:
        try:
            path = _normalize_path(raw)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        if not path.startswith("butler/") or not path.endswith(".py"):
            raise SystemExit(f"Invalid path: {raw!r}")
        if path in gate_existing:
            print(f"skip gate (exists): {path}", file=sys.stderr)
        else:
            new_gate.append(path)
            gate_existing.add(path)
        mod = _module_name(path)
        if mod in py_existing:
            print(f"skip pyproject (exists): {mod}", file=sys.stderr)
        else:
            new_py.append(mod)
            py_existing.add(mod)

    if not new_gate and not new_py:
        print("Nothing to append")
        return

    if args.dry_run:
        for p in new_gate:
            print(f"gate: {p}")
        for m in new_py:
            print(f"pyproject: {m}")
        return

    if new_gate:
        gate_text = gate_text.replace(
            ")\n\necho \"== Butler mypy strict gate",
            "".join(f"  {p}\n" for p in new_gate)
            + ")\n\necho \"== Butler mypy strict gate",
            1,
        )
        GATE.write_text(gate_text, encoding="utf-8")

    if new_py:
        insert = "".join(f'    "{m}",\n' for m in new_py)
        py_text = py_text.replace(
            "]\nstrict = true\n\n[tool.coverage.run]",
            insert + "]\nstrict = true\n\n[tool.coverage.run]",
            1,
        )
        PYPROJECT.write_text(py_text, encoding="utf-8")

    print(f"Appended {len(new_gate)} gate + {len(new_py)} pyproject modules")


if __name__ == "__main__":
    main()
