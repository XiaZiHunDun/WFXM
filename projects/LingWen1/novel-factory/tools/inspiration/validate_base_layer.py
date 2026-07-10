#!/usr/bin/env python3
"""Validate 灵感基础层 YAML against base_layer.schema.json.

用法:
    python validate_base_layer.py <path1.yaml> [path2.yaml ...]

退出码:
    0  全部文件通过校验
    1  至少一个文件有错误
    2  缺少依赖（jsonschema）或 schema 缺失

Schema 路径优先 ``tools/validators/base_layer.schema.json``（统一根），回退到旧
位置 ``tools/inspiration/base_layer.schema.json`` 以兼容既有调用与测试。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
_NEW_SCHEMA = _HERE.parent / "validators" / "base_layer.schema.json"
_OLD_SCHEMA = _HERE / "base_layer.schema.json"


def load_base_layer(path: Path) -> object:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML 解析失败: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"顶层必须是 mapping，实际是 {type(data).__name__}")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate 灵感基础层 YAML files.")
    ap.add_argument("paths", nargs="+", type=Path, help="基础层 YAML 文件路径")
    ap.add_argument("--quiet", action="store_true", help="成功后只打总数")
    args = ap.parse_args()

    schema_path = _NEW_SCHEMA if _NEW_SCHEMA.is_file() else _OLD_SCHEMA
    if not schema_path.is_file():
        print(f"[validator] 找不到 schema: {_NEW_SCHEMA}（也尝试了 {_OLD_SCHEMA}）",
              file=sys.stderr)
        return 2

    # 让 validators 包中的 _base 可被 import；本脚本可作为独立 script 跑，
    # 因此 sys.path 注入其父目录的父目录（validators/ 的同级 tools/ 之父）。
    sys.path.insert(0, str(_HERE.parent))
    from validators._base import format_cli_errors, run_validator

    # run_validator 会追加 .schema.json；strip 掉以避免 base_layer.schema.schema.json
    schema_name = schema_path.name.removesuffix(".schema.json")
    errs = run_validator(
        schema_name,
        args.paths,
        load_fn=load_base_layer,
        schema_root=schema_path.parent,
    )
    return format_cli_errors(errs, quiet_success=args.quiet, n_files=len(args.paths))


if __name__ == "__main__":
    sys.exit(main())