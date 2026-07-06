#!/usr/bin/env python3
"""Fix low-error modules and append to P2-F strict gate until target count."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/butler-mypy-strict-gate.sh"


def gate_modules() -> set[str]:
    text = GATE.read_text()
    return set(re.findall(r"butler/[^\s']+\.py", text))


def mypy_errors(path: Path) -> list[str]:
    r = subprocess.run(
        [sys.executable, "-m", "mypy", str(path), "--follow-imports=skip"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return [ln for ln in (r.stdout + r.stderr).splitlines() if ": error:" in ln]


def apply_common_fixes(path: Path) -> bool:
    src = path.read_text()
    orig = src
    # bool env_truthy returns
    src = re.sub(
        r"return env_truthy\(",
        "return bool(env_truthy(",
        src,
    )
    # list[dict] without type args in annotations
    src = re.sub(r"\blist\[dict\]", "list[dict[str, Any]]", src)
    src = re.sub(r"\bdict\](?!\[)", "dict[str, Any]]", src)  # noqa - too broad, skip
  # Only fix list[dict] which is the common pattern
    if "from typing import" in src and "Any" not in src.split("from typing import", 1)[1].split("\n", 1)[0]:
        src = re.sub(
            r"from typing import ([^\n]+)",
            lambda m: (
                f"from typing import {m.group(1)}, Any"
                if "Any" not in m.group(1)
                else m.group(0)
            ),
            src,
            count=1,
        )
    if src != orig:
        path.write_text(src)
        return True
    return False


def main() -> int:
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 180
    scan = subprocess.run(
        ["bash", str(ROOT / "scripts/p2f-low-error-scan.sh")],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    candidates: list[tuple[int, Path]] = []
    for line in scan.stdout.splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) != 2:
            continue
        cnt, rel = int(parts[0]), parts[1]
        candidates.append((cnt, ROOT / rel))

    in_gate = gate_modules()
    added: list[str] = []
    for _cnt, path in candidates:
        if len(in_gate) + len(added) >= target:
            break
        rel = str(path.relative_to(ROOT))
        if rel in in_gate:
            continue
        apply_common_fixes(path)
        errs = mypy_errors(path)
        if errs:
            continue
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/p2f-append-gate-modules.py"), rel],
            check=True,
            cwd=ROOT,
        )
        added.append(rel)
        in_gate.add(rel)

    print(f"Added {len(added)} modules; gate now ~{len(in_gate)}")
    for m in added:
        print(f"  + {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
