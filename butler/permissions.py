"""Declarative project permission rules (CC permissions.ts subset, no LLM classifier)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    action: str  # allow | deny | ask
    reason: str = ""


def _load_permissions_yaml(workspace: Path | None) -> dict[str, Any]:
    if workspace is None:
        return {}
    for rel in (".butler/permissions.yaml", ".butler/permissions.yml"):
        path = workspace / rel
        if path.is_file():
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except Exception as exc:
                logger.warning("permissions.yaml parse failed: %s", exc)
    proj = workspace / "project.yaml"
    if proj.is_file():
        try:
            data = yaml.safe_load(proj.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                perms = data.get("permissions")
                return perms if isinstance(perms, dict) else {}
        except Exception:
            pass
    return {}


def _match_glob(pattern: str, value: str) -> bool:
    pat = str(pattern or "").strip()
    if not pat:
        return False
    if pat.endswith("*"):
        return value.startswith(pat[:-1])
    return value == pat


def evaluate_permission(
    tool_name: str,
    args: dict[str, Any],
    *,
    workspace: Path | None = None,
) -> PermissionDecision | None:
    """Return None when no rule matches (fall through to plan_mode / owner)."""
    cfg = _load_permissions_yaml(workspace)
    rules = cfg.get("rules") or cfg.get("tool_rules")
    if not isinstance(rules, list):
        return None

    path_val = str(args.get("path") or args.get("file_path") or args.get("command") or "")
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        tool_pat = str(rule.get("tool") or rule.get("name") or "*")
        if tool_pat != "*" and tool_pat != tool_name:
            continue
        path_pat = rule.get("path") or rule.get("path_glob")
        if path_pat and not _match_glob(str(path_pat), path_val):
            continue
        cmd_re = rule.get("command_regex") or rule.get("bash_regex")
        if cmd_re and tool_name in ("terminal", "bash"):
            if not re.search(str(cmd_re), path_val):
                continue
        action = str(rule.get("action") or rule.get("decision") or "deny").lower()
        reason = str(rule.get("reason") or rule.get("message") or f"permission rule: {action}")
        if action == "allow":
            return PermissionDecision(allowed=True, action="allow", reason=reason)
        if action == "ask":
            return PermissionDecision(allowed=False, action="ask", reason=reason)
        return PermissionDecision(allowed=False, action="deny", reason=reason)
    return None


def check_project_permission_block(
    tool_name: str,
    args: dict[str, Any],
) -> str | None:
    """Return error message when denied; None if allowed or no rule."""
    try:
        from butler.execution_context import get_current_orchestrator
        from butler.execution_context import get_current_session_key

        orch = get_current_orchestrator()
        if orch is None:
            return None
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            return None
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            return None
        workspace = Path(proj.workspace)
    except Exception:
        return None

    decision = evaluate_permission(tool_name, args, workspace=workspace)
    if decision is None or decision.allowed:
        return None
    if decision.action == "ask":
        return f"{decision.reason}（需 Owner 确认后重试）"
    return decision.reason
