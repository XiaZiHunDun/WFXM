"""Declarative project permission rules (CC permissions.ts subset, no LLM classifier)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_PATH_TOOLS = frozenset(
    {
        "read_file",
        "write_file",
        "patch",
        "delete_file",
        "search_files",
        "list_dir",
    }
)


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    action: str  # allow | deny | ask
    reason: str = ""
    permission: str = ""  # e.g. external_directory, rule, workflow_step


def match_path_glob(pattern: str, value: str) -> bool:
    return _match_glob(pattern, value)


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


def _resolve_path_arg(args: dict[str, Any]) -> str:
    return str(args.get("path") or args.get("file_path") or "").strip()


def _path_outside_workspace(path_str: str, workspace: Path) -> bool:
    if not path_str:
        return False
    try:
        from butler.tools.path_safety import check_tool_path

        result = check_tool_path(path_str, for_write=False)
        if not result.allowed and "outside workspace" in (result.error or "").lower():
            return True
    except Exception:
        pass
    try:
        root = workspace.expanduser().resolve()
        target = Path(path_str).expanduser()
        if not target.is_absolute():
            target = (root / target).resolve()
        else:
            target = target.resolve()
        return not str(target).startswith(str(root))
    except Exception:
        return False
    return False


def evaluate_external_directory(
    path_str: str,
    *,
    workspace: Path | None,
    for_write: bool = False,
) -> PermissionDecision | None:
    """Rules for paths outside project workspace (OpenCode external_directory subset)."""
    if workspace is None or not path_str.strip():
        return None
    if not _path_outside_workspace(path_str, workspace):
        return None

    cfg = _load_permissions_yaml(workspace)
    rules = cfg.get("external_directory")
    if not isinstance(rules, list) or not rules:
        return PermissionDecision(
            allowed=False,
            action="deny",
            reason=f"路径在工作区外（outside workspace）：{path_str}",
            permission="external_directory",
        )

    matched: PermissionDecision | None = None
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        path_pat = rule.get("path") or rule.get("path_glob") or "*"
        if path_pat != "*" and not _match_glob(str(path_pat), path_str):
            continue
        if for_write and rule.get("read_only") is True:
            matched = PermissionDecision(
                allowed=False,
                action="deny",
                reason="external_directory 规则禁止写入",
                permission="external_directory",
            )
            continue
        action = str(rule.get("action") or rule.get("decision") or "ask").lower()
        reason = str(rule.get("reason") or rule.get("message") or f"external_directory: {action}")
        if action == "allow":
            matched = PermissionDecision(allowed=True, action="allow", reason=reason, permission="external_directory")
        elif action == "ask":
            matched = PermissionDecision(allowed=False, action="ask", reason=reason, permission="external_directory")
        else:
            matched = PermissionDecision(allowed=False, action="deny", reason=reason, permission="external_directory")
    return matched


def get_workflow_step_tool_allowlist(
    step_id: str,
    *,
    workspace: Path | None = None,
) -> set[str] | None:
    """Return allowed tool names for *step_id*, or None if step has no allowlist."""
    sid = str(step_id or "").strip()
    if not sid:
        return None
    cfg = _load_permissions_yaml(workspace)
    steps_cfg = cfg.get("workflow_steps")
    if not isinstance(steps_cfg, dict):
        return None
    step_rules = steps_cfg.get(sid)
    if step_rules is None:
        return None
    allowed = step_rules.get("tools") if isinstance(step_rules, dict) else step_rules
    if not isinstance(allowed, list) or not allowed:
        return None
    from butler.tools.project_tools import canonical_tool_name

    names = {canonical_tool_name(str(t)) for t in allowed if str(t).strip()}
    return {n for n in names if n}


def evaluate_workflow_step_permission(
    tool_name: str,
    step_id: str,
    *,
    workspace: Path | None = None,
) -> PermissionDecision | None:
    """Step-level tool whitelist from ``workflow_steps`` in permissions.yaml."""
    if not step_id.strip():
        return None
    cfg = _load_permissions_yaml(workspace)
    steps_cfg = cfg.get("workflow_steps")
    if not isinstance(steps_cfg, dict):
        return None
    step_rules = steps_cfg.get(step_id)
    if step_rules is None:
        return None
    allowed = step_rules.get("tools") if isinstance(step_rules, dict) else step_rules
    if not isinstance(allowed, list) or not allowed:
        return None
    allowed_set = {str(t).strip() for t in allowed if str(t).strip()}
    if tool_name in allowed_set:
        return PermissionDecision(allowed=True, action="allow", reason="workflow step allowlist", permission="workflow_step")
    return PermissionDecision(
        allowed=False,
        action="deny",
        reason=f"步骤 {step_id} 仅允许工具: {', '.join(sorted(allowed_set))}",
        permission="workflow_step",
    )


def _security_blacklist_enabled() -> bool:
    try:
        from butler.env_parse import env_truthy

        return env_truthy("BUTLER_PERMISSIONS_PARAM_BLACKLIST", default=True)
    except Exception:
        return True


def _arg_values_for_param(args: dict[str, Any], param: str) -> list[str]:
    key = str(param or "").strip()
    if not key or key == "*":
        return [str(v) for v in args.values() if v is not None]
    if key in args:
        val = args[key]
        if isinstance(val, (list, tuple)):
            return [str(x) for x in val]
        return [str(val)]
    return []


def evaluate_security_blacklist(
    tool_name: str,
    args: dict[str, Any],
    *,
    workspace: Path | None = None,
) -> PermissionDecision | None:
    """Parameter-level deny rules (LobeHub security_blacklist subset). Highest priority."""
    if not _security_blacklist_enabled():
        return None
    cfg = _load_permissions_yaml(workspace)
    rules = cfg.get("security_blacklist")
    if not isinstance(rules, list) or not rules:
        return None

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        tool_pat = str(rule.get("tool") or rule.get("name") or "*")
        if tool_pat != "*" and tool_pat != tool_name:
            continue
        param = str(rule.get("param") or rule.get("field") or "*")
        pattern = rule.get("pattern")
        pattern_re = rule.get("pattern_regex") or rule.get("regex")
        reason = str(
            rule.get("reason")
            or rule.get("message")
            or "security_blacklist: 参数被拒绝"
        )
        for val in _arg_values_for_param(args, param):
            text = str(val)
            if pattern is not None and str(pattern) in text:
                return PermissionDecision(
                    allowed=False,
                    action="deny",
                    reason=reason,
                    permission="security_blacklist",
                )
            if pattern_re:
                try:
                    if re.search(str(pattern_re), text, re.I):
                        return PermissionDecision(
                            allowed=False,
                            action="deny",
                            reason=reason,
                            permission="security_blacklist",
                        )
                except re.error as exc:
                    logger.warning("security_blacklist regex invalid: %s", exc)
    return None


def evaluate_tool_policy(
    tool_name: str,
    *,
    workspace: Path | None = None,
) -> PermissionDecision | None:
    """Per-tool HITL from ``tool_policies`` (LangChain/Dify subset)."""
    cfg = _load_permissions_yaml(workspace)
    policies = cfg.get("tool_policies") or cfg.get("tools")
    if not isinstance(policies, dict):
        return None
    raw = policies.get(tool_name)
    if raw is None:
        return None
    if isinstance(raw, str):
        action = raw.strip().lower()
        reason = f"tool_policies: {tool_name} -> {action}"
    elif isinstance(raw, dict):
        action = str(raw.get("action") or raw.get("decision") or "ask").lower()
        reason = str(raw.get("reason") or raw.get("message") or f"tool_policies: {action}")
    else:
        return None
    if action == "allow":
        return PermissionDecision(True, "allow", reason, permission="tool_policy")
    if action == "ask":
        return PermissionDecision(False, "ask", reason, permission="tool_policy")
    return PermissionDecision(False, "deny", reason, permission="tool_policy")


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

    path_val = _resolve_path_arg(args) or str(args.get("command") or "")
    matched: PermissionDecision | None = None
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
        perm = str(rule.get("permission") or "rule")
        if action == "allow":
            matched = PermissionDecision(allowed=True, action="allow", reason=reason, permission=perm)
        elif action == "ask":
            matched = PermissionDecision(allowed=False, action="ask", reason=reason, permission=perm)
        else:
            matched = PermissionDecision(allowed=False, action="deny", reason=reason, permission=perm)
    return matched


def _approval_request_from_decision(
    decision: PermissionDecision,
    tool_name: str,
    args: dict[str, Any],
) -> "ApprovalRequest":
    from butler.permission_approvals import ApprovalRequest

    path_val = _resolve_path_arg(args) or str(args.get("command") or "*")
    perm = str(decision.permission or "rule").strip() or "rule"
    return ApprovalRequest(
        permission=perm,
        tool=tool_name,
        pattern=path_val or "*",
        reason=decision.reason,
    )


def _decision_with_approval(
    decision: PermissionDecision,
    tool_name: str,
    args: dict[str, Any],
    *,
    session_key: str,
) -> PermissionDecision | None:
    """Return None if approved; else original decision."""
    if decision.action != "ask":
        return decision
    from butler.permission_approvals import ApprovalRequest, is_approved, save_pending

    req = _approval_request_from_decision(decision, tool_name, args)
    if session_key and is_approved(session_key, req):
        return None
    try:
        from butler.hooks.runner import run_permission_request_hooks

        hook_block = run_permission_request_hooks(
            tool_name,
            args,
            reason=decision.reason,
            session_key=session_key,
        )
        if hook_block:
            decision = PermissionDecision(
                allowed=False,
                action="deny",
                reason=hook_block,
                permission=decision.permission,
            )
            return decision
    except Exception:
        pass
    if session_key:
        save_pending(session_key, req)
    return decision


def check_external_path_override(
    path_str: str,
    *,
    for_write: bool = False,
) -> PermissionDecision | None:
    """If path is outside workspace, apply external_directory rules + session approvals."""
    workspace = _current_workspace()
    if workspace is None:
        return None
    decision = evaluate_external_directory(path_str, workspace=workspace, for_write=for_write)
    if decision is None:
        return None
    if decision.allowed:
        return decision
    session_key = _current_session_key()
    if decision.action == "ask":
        resolved = _decision_with_approval(decision, "path", {"path": path_str}, session_key=session_key)
        if resolved is None:
            return PermissionDecision(True, "allow", "session approval", permission="external_directory")
        return resolved
    return decision


def _current_workspace() -> Path | None:
    try:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        if orch is None:
            return None
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            return None
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            return None
        return Path(proj.workspace)
    except Exception:
        return None


def _current_session_key() -> str:
    try:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip()
    except Exception:
        return ""


def check_project_permission_block(
    tool_name: str,
    args: dict[str, Any],
) -> str | None:
    """Return error message when denied; None if allowed or no rule."""
    workspace = _current_workspace()
    if workspace is None:
        return None

    session_key = _current_session_key()

    bl = evaluate_security_blacklist(tool_name, args, workspace=workspace)
    if bl is not None and not bl.allowed:
        return bl.reason

    try:
        from butler.experiments.mode import check_experiment_mode_block

        exp_block = check_experiment_mode_block(tool_name, args, workspace=workspace)
        if exp_block:
            return exp_block
    except Exception:
        pass

    try:
        from butler.execution_context import get_current_workflow_step

        step_id = get_current_workflow_step()
        if step_id:
            step_decision = evaluate_workflow_step_permission(
                tool_name,
                step_id,
                workspace=workspace,
            )
            if step_decision is not None and not step_decision.allowed:
                return step_decision.reason
    except Exception:
        pass

    path_val = _resolve_path_arg(args)
    if path_val and tool_name in _PATH_TOOLS:
        ext = evaluate_external_directory(path_val, workspace=workspace, for_write=tool_name in ("write_file", "patch", "delete_file"))
        if ext is not None:
            if ext.allowed:
                pass
            elif ext.action == "ask":
                blocked = _decision_with_approval(ext, tool_name, args, session_key=session_key)
                if blocked is not None:
                    return _format_ask_message(blocked)
            else:
                return ext.reason

    policy = evaluate_tool_policy(tool_name, workspace=workspace)
    if policy is not None:
        if policy.allowed:
            pass
        elif policy.action == "ask":
            blocked = _decision_with_approval(policy, tool_name, args, session_key=session_key)
            if blocked is not None:
                return _format_ask_message(blocked)
        else:
            return policy.reason

    decision = evaluate_permission(tool_name, args, workspace=workspace)
    if decision is None or decision.allowed:
        return None
    if decision.action == "ask":
        blocked = _decision_with_approval(decision, tool_name, args, session_key=session_key)
        if blocked is None:
            return None
        return _format_ask_message(blocked)
    return decision.reason


def _format_ask_message(decision: PermissionDecision) -> str:
    perm = str(decision.permission or "rule")
    return (
        f"{decision.reason}（需 Owner：/批准一次 或 /始终允许 {perm}）"
    )
