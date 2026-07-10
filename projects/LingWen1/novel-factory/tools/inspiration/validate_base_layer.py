#!/usr/bin/env python3
"""Validate 灵感基础层 YAML against base_layer.schema.json.

用法:
    python validate_base_layer.py <path1.yaml> [path2.yaml ...]

退出码:
    0  全部文件通过校验
    1  至少一个文件有错误
    2  缺少依赖（jsonschema）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

try:
    import jsonschema
except ImportError:
    sys.exit(
        "缺少 jsonschema 依赖；请 pip install 'jsonschema>=4.20,<5'\n"
        "（项目级 dev 依赖见 pyproject.toml [project.optional-dependencies] dev 组）"
    )


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "tools" / "inspiration" / "base_layer.schema.json"


def _load_schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _format_error(err: jsonschema.ValidationError) -> str:
    path = "/".join(str(p) for p in err.absolute_path) or "(root)"
    return f"{path}: {err.message}"


def validate_file(path: Path, schema: dict) -> list[str]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"YAML 解析失败: {exc}"]
    if not isinstance(data, dict):
        return [f"顶层必须是 mapping，实际是 {type(data).__name__}"]
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{path}: {_format_error(e)}" for e in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))]


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate 灵感基础层 YAML files.")
    ap.add_argument("paths", nargs="+", type=Path, help="基础层 YAML 文件路径")
    ap.add_argument("--quiet", action="store_true", help="成功后只打总数")
    args = ap.parse_args()

    if not SCHEMA.is_file():
        print(f"[validator] 找不到 schema: {SCHEMA}", file=sys.stderr)
        return 2

    schema = _load_schema()
    all_errors: list[str] = []
    for p in args.paths:
        all_errors.extend(validate_file(p, schema))

    if all_errors:
        for e in all_errors:
            print(e, file=sys.stderr)
        print(f"\n✗ {len(all_errors)} error(s) across {len(args.paths)} file(s)", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"✓ {len(args.paths)} file(s) validated against {SCHEMA.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())