#!/usr/bin/env python3
"""Apply mypy-guided micro-fixes to *_ops.py (P5 wave3)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def mypy_errors(path: Path) -> list[tuple[int, str]]:
    r = subprocess.run(
        [sys.executable, "-m", "mypy", str(path), "--follow-imports=skip", "--strict"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    out = []
    for ln in (r.stdout + r.stderr).splitlines():
        m = re.search(r":(\d+): error: (.+)$", ln)
        if m:
            out.append((int(m.group(1)), m.group(2)))
    return out


def ensure_any_import(src: str) -> str:
    if re.search(r"from typing import[^\n]*\bAny\b", src):
        return src
    if "from typing import" in src:
        return re.sub(r"(from typing import [^\n]+)", r"\1, Any", src, count=1)
    return "from typing import Any\n" + src


def ensure_cast_import(src: str) -> str:
    if re.search(r"from typing import[^\n]*\bcast\b", src):
        return src
    if "from typing import" in src:
        return re.sub(r"(from typing import [^\n]+)", r"\1, cast", src, count=1)
    return "from typing import cast\n" + src


def fix_file(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    errors = mypy_errors(path)
    if not errors:
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    changed = False
    for lineno, err in errors:
        idx = lineno - 1
        if idx < 0 or idx >= len(lines):
            continue
        line = lines[idx]
        if "import-untyped" in err and "yaml" in line:
            if "type: ignore" not in line:
                lines[idx] = line.replace("import yaml", "import yaml  # type: ignore[import-untyped]")
                changed = True
        elif "import-untyped" in err and "qrcode" in line:
            if "type: ignore" not in line:
                lines[idx] = line.replace("import qrcode", "import qrcode  # type: ignore[import-untyped]")
                changed = True
        elif "import-not-found" in err and "butler.core.session_key" in line:
            lines[idx] = line.replace("butler.core.session_key", "butler.execution_context")
            changed = True
        elif "Missing type arguments" in err and "dict" in err:
            lines[idx] = re.sub(r"\bdict\b(?!\[)", "dict[str, Any]", line)
            changed = True
        elif "Missing type arguments" in err and "list" in err:
            lines[idx] = re.sub(r"\blist\b(?!\[)", "list[Any]", line)
            changed = True
        elif "no-any-return" in err and line.strip().startswith("return "):
            expr = line.strip()[7:]
            if "-> str" in err or 'return "str"' in err or "str |" in err:
                if not expr.startswith("str("):
                    lines[idx] = line.replace(f"return {expr}", f"return str({expr})")
                    changed = True
            elif "-> bool" in err:
                if not expr.startswith("bool("):
                    lines[idx] = line.replace(f"return {expr}", f"return bool({expr})")
                    changed = True
            elif "-> int" in err and "int |" not in err:
                if not expr.startswith("int("):
                    lines[idx] = line.replace(f"return {expr}", f"return int({expr})")
                    changed = True
            elif "Path" in err:
                if "cast(" not in expr:
                    lines[idx] = line.replace(f"return {expr}", f"return cast(Path, {expr})")
                    changed = True
        elif "return safe_best_effort(" in line:
            # skip - handled manually
            pass
    if changed:
        src = "\n".join(lines) + ("\n" if path.read_text(encoding="utf-8").endswith("\n") else "")
        if "dict[str, Any]" in src or "list[Any]" in src:
            src = ensure_any_import(src)
        if "cast(Path," in src:
            src = ensure_cast_import(src)
        path.write_text(src, encoding="utf-8")
    return changed


def main() -> int:
    strict = {
        ln.strip()
        for ln in (ROOT / "scripts/p5_ops_strict_modules.txt").read_text().splitlines()
        if ln.strip()
    }
    targets = [
        p
        for p in sorted((ROOT / "butler").rglob("*_ops.py"))
        if str(p.relative_to(ROOT)).replace("\\", "/") not in strict
    ]
    rounds = 0
    total = 0
    while rounds < 5:
        rounds += 1
        n = 0
        for p in targets:
            if fix_file(p):
                n += 1
                print("fixed", p.relative_to(ROOT))
        total += n
        if n == 0:
            break
    print(f"rounds={rounds} file-fixes={total}")
    remaining = sum(1 for p in targets if mypy_errors(p))
    print(f"remaining failing files: {remaining}/{len(targets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
