#!/usr/bin/env python3
"""P5 *_ops.py modules passing mypy --strict (--follow-imports=skip).

Regenerate: python3 scripts/p5_ops_strict_modules.py --refresh
Gate reads scripts/p5_ops_strict_modules.txt (committed).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST_FILE = ROOT / "scripts" / "p5_ops_strict_modules.txt"

EXTRA_MODULES = ("butler/repo_paths.py",)


def _passes_strict(path: Path) -> bool:
    r = subprocess.run(
        [sys.executable, "-m", "mypy", str(path), "--follow-imports=skip", "--strict"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def _scan_paths() -> list[str]:
    paths: list[str] = []
    for p in sorted(ROOT.joinpath("butler").rglob("*_ops.py")):
        if _passes_strict(p):
            paths.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    for rel in EXTRA_MODULES:
        p = ROOT / rel
        if p.is_file() and _passes_strict(p):
            paths.append(rel)
    return sorted(set(paths))


def _load_committed() -> list[str]:
    return [
        ln.strip()
        for ln in LIST_FILE.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]


def path_to_module(rel: str) -> str:
    return rel.removesuffix(".py").replace("/", ".")


def main() -> int:
    if "--refresh" in sys.argv:
        paths = _scan_paths()
        LIST_FILE.write_text("\n".join(paths) + "\n", encoding="utf-8")
        print(f"Wrote {len(paths)} paths to {LIST_FILE.relative_to(ROOT)}")
        return 0

    paths = _load_committed()
    if "--modules" in sys.argv:
        for rel in paths:
            print(path_to_module(rel))
        return 0
    for rel in paths:
        print(rel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
