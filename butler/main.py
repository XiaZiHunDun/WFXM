#!/usr/bin/env python3
"""Butler CLI — project + model layer on top of Hermes-Agent."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _hermes_command() -> list[str]:
    exe = shutil.which("hermes")
    if exe:
        return [exe]
    return [sys.executable, str(_REPO_ROOT / "hermes_cli" / "main.py")]


def _platform_env_from_csv(raw: str) -> dict[str, str]:
    if not raw.strip():
        return {}
    normalized: list[str] = []
    for part in raw.split(","):
        token = part.strip().lower()
        if not token:
            continue
        if token in ("wechat", "weixin"):
            normalized.append("weixin")
        else:
            normalized.append(token)
    return {"BUTLER_GATEWAY_PLATFORMS": ",".join(normalized)}


def _butler_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    from butler.project_manager import get_project_manager

    env = os.environ.copy()
    env["BUTLER_WORKSPACE_ROOT"] = str(_REPO_ROOT.resolve())
    pm = get_project_manager()
    if proj := pm.get_current():
        env["BUTLER_PROJECT"] = proj.name
        env["BUTLER_PROJECT_ROOT"] = str(proj.workspace)
    if extra:
        env.update(extra)
    return env


def _invoke_hermes(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    env_extra: dict[str, str] | None = None,
) -> int:
    argv = [*_hermes_command(), *args]
    result = subprocess.run(
        argv,
        env=_butler_env(env_extra),
        cwd=str(cwd or _REPO_ROOT),
    )
    return int(result.returncode)


def _cmd_chat(_ns: argparse.Namespace) -> int:
    return _invoke_hermes(["chat"])


def _cmd_projects(_ns: argparse.Namespace) -> int:
    from butler.project_manager import get_project_manager

    manager = get_project_manager()
    projects = sorted(manager.list_projects(), key=lambda p: p.name)
    if not projects:
        print("No projects found.", file=sys.stderr)
        print(f"Projects directory: {manager.projects_dir}", file=sys.stderr)
        return 0
    current = manager.current_project
    for proj in projects:
        mark = "*" if proj.name == current else " "
        print(f"[{mark}] {proj.name:20} ({proj.type:8})  {proj.workspace}")
    return 0


def _cmd_create(ns: argparse.Namespace) -> int:
    from butler.project_manager import get_project_manager

    mgr = get_project_manager()
    created = mgr.create_project(ns.name, ns.type_, ns.description)
    if created is None:
        print(f"Project {ns.name!r} already exists.", file=sys.stderr)
        return 1
    print(f"Created project {created.name} at {created.workspace}")
    return 0


def _cmd_gateway(ns: argparse.Namespace) -> int:
    extra_env = _platform_env_from_csv(ns.platforms)
    args = ["gateway", *ns.hermes_remainder]
    if not ns.hermes_remainder:
        args.append("run")
    return _invoke_hermes(args, env_extra=extra_env or None)


def _cmd_wechat_setup(_ns: argparse.Namespace) -> int:
    try:
        try:
            from hermes_logging import setup_logging as _setup_logging

            _setup_logging(mode="cli")
        except Exception:
            pass
        from hermes_cli.gateway import _setup_weixin
    except ImportError as exc:
        print(
            "WeChat setup requires the Hermes CLI and gateway extras to be installed:\n"
            f"  {exc}",
            file=sys.stderr,
        )
        return 1
    _setup_weixin()
    return 0


def _cmd_exec(ns: argparse.Namespace) -> int:
    return _invoke_hermes(["-z", ns.message])


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="butler",
        description="Butler v2 — multi-project layer on Hermes-Agent.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    chat = sub.add_parser("chat", help="Interactive Hermes chat with Butler project context")
    chat.set_defaults(func=_cmd_chat)

    sub.add_parser("projects", help="List known projects").set_defaults(func=_cmd_projects)

    cr = sub.add_parser("create", help="Create a new project under projects/")
    cr.add_argument("name", help="Project directory / logical name")
    cr.add_argument("--type", dest="type_", default="software", help="Project type")
    cr.add_argument("--description", default="", help="Short description")
    cr.set_defaults(func=_cmd_create)

    gw = sub.add_parser(
        "gateway",
        help="Start the Hermes messaging gateway (default: foreground run)",
    )
    gw.add_argument(
        "--platforms",
        default="",
        help="Comma-separated hint (e.g. wechat) — sets BUTLER_GATEWAY_PLATFORMS",
    )
    gw.add_argument(
        "hermes_remainder",
        nargs=argparse.REMAINDER,
        help="Extra args forwarded to `hermes gateway ...` (leading `--` recommended)",
    )
    gw.set_defaults(func=_cmd_gateway)

    sub.add_parser("wechat-setup", help="Weixin / WeChat QR login (Hermes gateway)").set_defaults(
        func=_cmd_wechat_setup
    )

    ex = sub.add_parser("exec", help="Single-shot agent message (`hermes -z`)")
    ex.add_argument("message", help="User message / instruction")
    ex.set_defaults(func=_cmd_exec)

    return p


def main(argv: Sequence[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
