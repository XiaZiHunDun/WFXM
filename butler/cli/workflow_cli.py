"""CLI: ``butler workflow validate``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_workflow_validate(ns: argparse.Namespace) -> int:
    from butler.workflows.validate import (
        WORKFLOW_SCHEMA_VERSION,
        validate_project_workflow,
        validate_workflow_file,
    )

    errors: list[str] = []
    wf_name = ""
    if ns.path:
        path = Path(ns.path).expanduser().resolve()
        _wf, errors = validate_workflow_file(path)
        wf_name = path.name
    elif ns.workflow:
        from butler.project.manager import get_project_manager

        pm = get_project_manager()
        project = None
        if ns.project:
            project = pm.get_by_name(ns.project)
            if project is None:
                print(f"未知项目: {ns.project}", file=sys.stderr)
                return 2
        else:
            project = pm.get_current()
        if project is None:
            print("未选择项目；请 --project 或先 /切换", file=sys.stderr)
            return 2
        wf_name = ns.workflow
        errors = validate_project_workflow(project, wf_name)
    else:
        print("需要 --path 或 --workflow", file=sys.stderr)
        return 2

    if ns.json:
        print(
            json.dumps(
                {
                    "schema_version": WORKFLOW_SCHEMA_VERSION,
                    "workflow": wf_name,
                    "ok": not errors,
                    "errors": errors,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if not errors else 1

    if errors:
        print(f"workflow validate FAILED ({wf_name})")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"workflow validate OK ({wf_name}) schema={WORKFLOW_SCHEMA_VERSION}")
    return 0


def register_workflow_subparser(sub: argparse._SubParsersAction) -> None:
    wf = sub.add_parser("workflow", help="工作流工具")
    wf_sub = wf.add_subparsers(dest="workflow_cmd", required=True)
    val = wf_sub.add_parser("validate", help="校验 workflow YAML / 项目登记")
    val.add_argument("--path", default="", help=".butler/workflows/*.yaml 路径")
    val.add_argument("--workflow", default="", help="项目内 workflow 名称")
    val.add_argument("--project", default="", help="项目显示名")
    val.add_argument("--json", action="store_true", help="JSON 输出")
    val.set_defaults(func=cmd_workflow_validate)
