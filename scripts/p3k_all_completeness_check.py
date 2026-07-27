#!/usr/bin/env python3
"""P3-K: audit __all__ completeness for shim and barrel files."""

from __future__ import annotations

import ast
import pathlib


def _has_deprecation_warning(text: str) -> bool:
    return "DeprecationWarning" in text


def _analyze_file(path: pathlib.Path) -> dict[str, list[str]] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None

    all_values: list[str] = []
    exported_names: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    try:
                        if isinstance(node.value, ast.List):
                            all_values = [
                                elt.value for elt in node.value.elts
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                            ]
                        elif isinstance(node.value, ast.Constant) and isinstance(node.value.value, list):
                            all_values = [str(v) for v in node.value.value]
                    except (AttributeError, ValueError):
                        pass

        if isinstance(node, ast.FunctionDef):
            if not node.name.startswith("_"):
                exported_names.append(node.name)
        elif isinstance(node, ast.AsyncFunctionDef):
            if not node.name.startswith("_"):
                exported_names.append(node.name)
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                exported_names.append(node.name)

    return {
        "path": str(path),
        "has_all": bool(all_values),
        "all_values": all_values,
        "exported_names": exported_names,
        "missing_in_all": sorted(set(exported_names) - set(all_values)),
        "extra_in_all": sorted(set(all_values) - set(exported_names)),
        "is_shim": _has_deprecation_warning(text),
    }


def main() -> int:
    root = pathlib.Path("butler")
    results: list[dict[str, list[str]]] = []

    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue

        is_barrel = path.name == "__init__.py"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        is_shim = _has_deprecation_warning(text)

        if not is_barrel and not is_shim:
            continue

        result = _analyze_file(path)
        if result:
            results.append(result)

    missing_count = sum(len(r["missing_in_all"]) for r in results)
    extra_count = sum(len(r["extra_in_all"]) for r in results)

    print("=== P3-K __all__ completeness report ===")
    print(f"Barrel + shim files: {len(results)}")
    print(f"Missing in __all__: {missing_count}")
    print(f"Extra in __all__: {extra_count}")
    print()

    print("Barrel/shim files with incomplete __all__ (missing names):")
    for r in sorted(results, key=lambda x: x["path"]):
        if r["missing_in_all"]:
            label = "[shim]" if r["is_shim"] else "[barrel]"
            print(f"  {label} {r['path']}:")
            for name in r["missing_in_all"]:
                print(f"    - {name}")
    print()

    print("Barrel/shim files with extra names in __all__ (should remove):")
    for r in sorted(results, key=lambda x: x["path"]):
        if r["extra_in_all"]:
            label = "[shim]" if r["is_shim"] else "[barrel]"
            print(f"  {label} {r['path']}:")
            for name in r["extra_in_all"]:
                print(f"    - {name}")

    if missing_count > 0 or extra_count > 0:
        print(f"\nWARNING: {missing_count} missing + {extra_count} extra names found.")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())