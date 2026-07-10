#!/usr/bin/env python3
"""Unified dispatcher for novel-factory Agent output validators.

用法:
    python validate_all.py {writer|reviewer|inspiration} <paths...> [--quiet]

等价于直接调用对应 ``validate_<suite>.py``；用于在 CI / 微信指令中按 suite
聚合调用，避免重复写 N 行入口。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TOOLS = _HERE.parent


def _dispatch_writer(paths: list[Path], quiet: bool) -> int:
    sys.path.insert(0, str(_HERE))
    from validate_writer_chapter import (
        format_cli_errors,
        load_chapter,
        run_validator,
    )

    errs = run_validator("writer_chapter", paths, load_fn=load_chapter)
    return format_cli_errors(errs, quiet_success=quiet, n_files=len(paths))


def _dispatch_reviewer(paths: list[Path], quiet: bool) -> int:
    sys.path.insert(0, str(_HERE))
    from validate_reviewer_report import (
        format_cli_errors,
        load_reviewer_report,
        run_validator,
    )

    errs = run_validator("reviewer_report", paths, load_fn=load_reviewer_report)
    return format_cli_errors(errs, quiet_success=quiet, n_files=len(paths))


def _dispatch_inspiration(paths: list[Path], quiet: bool) -> int:
    sys.path.insert(0, str(_TOOLS / "inspiration"))
    sys.path.insert(0, str(_TOOLS))
    from validate_base_layer import load_base_layer
    from validators._base import format_cli_errors, run_validator

    schema_path = _HERE / "base_layer.schema.json"
    if not schema_path.is_file():
        schema_path = _TOOLS / "inspiration" / "base_layer.schema.json"
    schema_name = schema_path.name.removesuffix(".schema.json")
    errs = run_validator(
        schema_name, paths, load_fn=load_base_layer, schema_root=schema_path.parent
    )
    return format_cli_errors(errs, quiet_success=quiet, n_files=len(paths))


_DISPATCH = {
    "writer": _dispatch_writer,
    "reviewer": _dispatch_reviewer,
    "inspiration": _dispatch_inspiration,
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Unified dispatcher for novel-factory Agent validators.",
    )
    ap.add_argument(
        "suite",
        choices=sorted(_DISPATCH.keys()),
        help="writer=作家章节 / reviewer=审核报告 / inspiration=基础层",
    )
    ap.add_argument("paths", nargs="+", type=Path, help="待校验文件路径")
    ap.add_argument("--quiet", action="store_true", help="成功后只打总数")
    args = ap.parse_args()

    return _DISPATCH[args.suite](args.paths, args.quiet)


if __name__ == "__main__":
    sys.exit(main())