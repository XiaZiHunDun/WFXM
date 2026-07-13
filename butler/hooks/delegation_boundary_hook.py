"""P1 #4 — content vs dev 委派边界 hook。

读 stdin JSON（tool_name + tool_input）+ os.environ["BUTLER_AGENT_ROLE"]，
按 projects/<slug>/.butler/permissions.yaml delegation.<role>.write_allow/deny
判定；deny 优先于 allow；越界 exit(2) + stderr + audit log。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_LOG = REPO_ROOT / "butler" / "audit" / "delegation-violations.log"

WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}


def _normalize(path: str) -> str:
    """归一化路径：小写 + posix。"""
    return Path(path).as_posix()


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch(path, p) for p in patterns)


def _load_delegation(slug: str) -> dict | None:
    """读项目 permissions.yaml 的 delegation 段；不存在返回 None（fail-open）。

    优先 tracked 配置 `projects/<slug>/config/permissions.yaml`；
    fallback 到 runtime `.butler/permissions.yaml`（gitignore 内部态）。
    """
    tracked = REPO_ROOT / "projects" / slug / "config" / "permissions.yaml"
    runtime = REPO_ROOT / "projects" / slug / ".butler" / "permissions.yaml"
    yaml_path = tracked if tracked.exists() else runtime
    if not yaml_path.exists():
        return None
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return data.get("delegation")


def _audit(role: str, path: str, project: str) -> None:
    """写一条结构化 JSONL 到 audit log（演示可 tail 看）。"""
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "role": role,
        "path": path,
        "project": project,
    }
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _run_for_test() -> int:
    """单测入口：复用 _decide 逻辑。"""
    return _decide(json.loads(sys.stdin.read() or "{}"))


def _decide(payload: dict) -> int:
    """核心判定：返回 0（放行）或 2（拒绝）。"""
    role = os.environ.get("BUTLER_AGENT_ROLE")
    if role not in {"content", "dev"}:
        return 0  # Lead 本体 / 未声明 role → 静默放行

    project = os.environ.get("BUTLER_ACTIVE_PROJECT", "灵文1号")
    tool_name = payload.get("tool_name", "")
    if tool_name not in WRITE_TOOLS:
        return 0  # 只拦 Write 类工具

    path_raw = payload.get("tool_input", {}).get("file_path", "")
    if not path_raw:
        return 0  # 没指定路径 → 放行
    path = _normalize(path_raw)

    delegation = _load_delegation(project)
    if delegation is None:
        print(
            f"[P1#4 delegation boundary] WARN: projects/{project}/.butler/permissions.yaml 无 delegation 段，role={role} 默认放行 path={path}",
            file=sys.stderr,
        )
        return 0

    rules = delegation.get(role)
    if rules is None:
        return 0  # 没声明该 role → 放行

    deny = rules.get("write_deny", [])
    allow = rules.get("write_allow", [])

    if _matches_any(path, deny):
        _audit(role, path, project)
        print(
            f"[P1#4 delegation boundary] DENY: role={role} 不允许写 path={path}（deny 规则命中）。请确认 role 注入正确或重新委派。",
            file=sys.stderr,
        )
        return 2
    if not _matches_any(path, allow):
        _audit(role, path, project)
        print(
            f"[P1#4 delegation boundary] DENY: role={role} 写 path={path} 不在 write_allow 白名单。请确认 role 注入正确或重新委派。",
            file=sys.stderr,
        )
        return 2
    return 0


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0  # stdin 不是 JSON → 不破坏 Claude Code
    return _decide(payload)


if __name__ == "__main__":
    sys.exit(main())