"""CLI: ``butler provider`` preset commands."""

from __future__ import annotations

import argparse
from pathlib import Path


def register_provider_presets_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    prov = sub.add_parser("provider", help="模型 provider 预设（butler://）")
    sp = prov.add_subparsers(dest="provider_cmd", required=True)
    p_list = sp.add_parser("presets", help="列出 butler:// 预设")
    p_list.set_defaults(func=_cmd_presets)

    p_apply = sp.add_parser("apply", help="将预设写入 project.yaml")
    p_apply.add_argument("preset_id", help="preset_id 或 butler://…")
    p_apply.add_argument(
        "--role",
        default="dev_agent",
        help="模型角色（dev_agent / content_agent / review_agent / butler）",
    )
    p_apply.add_argument("--workspace", default="", help="项目工作区（含 project.yaml）")
    p_apply.add_argument(
        "--runtime",
        action="store_true",
        help="仅写 runtime 覆盖，不改 project.yaml",
    )
    p_apply.add_argument("--dry-run", action="store_true", help="预览，不写文件")
    p_apply.set_defaults(func=_cmd_apply)


def _cmd_presets(_ns: argparse.Namespace) -> int:
    from butler.provider_presets import format_presets_list

    print(format_presets_list())
    return 0


def _cmd_apply(ns: argparse.Namespace) -> int:
    from butler.provider_presets import apply_provider_preset
    from butler.project import Project

    workspace = None
    project = None
    raw_ws = str(getattr(ns, "workspace", "") or "").strip()
    if raw_ws:
        workspace = Path(raw_ws).expanduser()
        cfg = workspace / "project.yaml"
        if cfg.is_file():
            project = Project.from_yaml(cfg)

    ok, msg = apply_provider_preset(
        ns.preset_id,
        role=str(getattr(ns, "role", "dev_agent") or "dev_agent"),
        project=project,
        workspace=workspace if project is None else None,
        persist=not bool(getattr(ns, "runtime", False)),
        dry_run=bool(getattr(ns, "dry_run", False)),
    )
    print(msg)
    return 0 if ok else 1
