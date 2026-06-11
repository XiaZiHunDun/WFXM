"""Declarative project permission rules (CC permissions.ts subset, no LLM classifier)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.permissions.approvals import ApprovalRequest

import yaml

logger = logging.getLogger(__name__)

# R2-11: uniform fail-closed for permission check failures. The buffer holds
# the most recent failures so /诊断 can surface them (otherwise a malfunctioning
# experiment-mode detector or step resolver silently disables safety controls).
_MAX_PERMISSION_FAILURE_ENTRIES = 50
_MAX_PERMISSION_FAILURE_ERROR_LEN = 200
_permission_failures: list[dict[str, Any]] = []


def recent_permission_failures() -> list[dict[str, Any]]:
    """Read the module-level permission-failure diagnostics buffer."""
    return list(_permission_failures)


def reset_permission_failures() -> None:
    """Clear the permission-failure diagnostics buffer (test helper)."""
    _permission_failures.clear()


def _record_permission_failure(check: str, exc: BaseException) -> None:
    """Append a permission-check failure to the diagnostics buffer (FIFO bounded)."""
    logger.error(
        "Permission check %s failed (fail-closed); %s",
        check,
        exc,
        exc_info=exc,
    )
    _permission_failures.append({
        "check": check,
        "error": str(exc)[:_MAX_PERMISSION_FAILURE_ERROR_LEN],
        "type": type(exc).__name__,
    })
    if len(_permission_failures) > _MAX_PERMISSION_FAILURE_ENTRIES:
        del _permission_failures[
            : len(_permission_failures) - _MAX_PERMISSION_FAILURE_ENTRIES
        ]


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
        except Exception as exc:
            logger.debug("load permissions yaml skipped: %s", exc)
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
    except Exception as exc:
        logger.warning("path_outside_workspace check failed (fail-closed): %s", exc)
        return True
    try:
        root = workspace.expanduser().resolve()
        target = Path(path_str).expanduser()
        if not target.is_absolute():
            target = (root / target).resolve()
        else:
            target = target.resolve()
        # Sprint 21-1 SEC-21-A-1: 用 is_relative_to 替换裸 startswith.
        # str(target).startswith(str(root)) 漏判 sibling-prefix 场景
        # (workspace=/tmp/proj, target=/tmp/proj_evil/x.md 会被误判为
        # inside) + 跨平台大小写不敏感 + /tmp symlink. is_relative_to
        # 做 path component 级比较, 行为统一. 镜像 Sprint 20-3
        # quarantine_bundle 修复 (Sprint 21-4 uninstall_skill 进一步统一).
        return not target.is_relative_to(root)
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
    allowed_set = get_workflow_step_tool_allowlist(step_id, workspace=workspace)
    if allowed_set is None:
        return None
    from butler.tools.project_tools import canonical_tool_name

    tool_key = canonical_tool_name(tool_name)
    if tool_key in allowed_set:
        return PermissionDecision(
            allowed=True,
            action="allow",
            reason="workflow step allowlist",
            permission="workflow_step",
        )
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
        logger.debug(
            "evaluate_permission: no rules found for workspace %s, allowing %s",
            workspace,
            tool_name,
        )
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
    from butler.permissions.approvals import ApprovalRequest

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
    from butler.permissions.approvals import is_approved, save_pending

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
    except Exception as exc:
        logger.warning("Permission request hooks failed (continuing): %s", exc)
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
        if orch is not None:
            pm = getattr(orch, "project_manager", None)
            if pm is not None:
                proj = pm.get_current(session_key=str(get_current_session_key() or ""))
                if proj is not None:
                    return Path(proj.workspace)
    except Exception:
        pass
    try:
        import os

        raw = os.getenv("BUTLER_TOOL_SAFE_ROOT", "").strip()
        if raw:
            p = Path(raw).expanduser()
            if p.is_dir():
                return p.resolve()
    except Exception:
        pass
    return None


def _current_session_key() -> str:
    try:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip()
    except Exception:
        return ""


def _experiment_block_or_fail_closed(
    tool_name: str,
    args: dict[str, Any],
    workspace: Path,
) -> str | None:
    """Run ``check_experiment_mode_block``; fail-CLOSED on detector error.

    Returns a block reason string when the experiment-mode detector blocks
    the call OR raises. The previous implementation caught detector errors
    and continued, silently disabling a safety control. Fail-closed means a
    broken detector blocks the call until the detector is repaired, never
    silently bypasses it.
    """
    try:
        from butler.experiments.mode import check_experiment_mode_block
    except Exception as exc:
        _record_permission_failure("experiment_mode_block_import", exc)
        return "experiment mode 守护不可用 (import 失败); 拒绝该调用"
    try:
        return check_experiment_mode_block(tool_name, args, workspace=workspace)
    except Exception as exc:
        _record_permission_failure("experiment_mode_block", exc)
        return "experiment mode 守护异常 (fail-closed); 拒绝该调用"


def _workflow_step_block_or_fail_closed(
    tool_name: str,
    workspace: Path,
) -> str | None:
    """Resolve the current workflow step + apply allowlist; fail-CLOSED on error.

    If the step resolver raises, we cannot determine which step's allowlist
    applies, so the safe default is to deny. A broken resolver must not
    silently widen the allowlist to "all tools".
    """
    try:
        from butler.execution_context import get_current_workflow_step
    except Exception as exc:
        _record_permission_failure("workflow_step_resolve_import", exc)
        return "workflow step 解析器不可用 (import 失败); 拒绝该调用"
    try:
        step_id = get_current_workflow_step()
    except Exception as exc:
        _record_permission_failure("workflow_step_resolve", exc)
        return "workflow step 解析器异常 (fail-closed); 拒绝该调用"
    if not step_id:
        return None
    try:
        step_decision = evaluate_workflow_step_permission(
            tool_name, step_id, workspace=workspace,
        )
    except Exception as exc:
        _record_permission_failure("workflow_step_decision", exc)
        return "workflow step 决策异常 (fail-closed); 拒绝该调用"
    if step_decision is not None and not step_decision.allowed:
        return step_decision.reason
    return None


def _apply_decision_or_none(
    decision: PermissionDecision | None,
    tool_name: str,
    args: dict[str, Any],
    *,
    session_key: str,
) -> str | None:
    """Translate one PermissionDecision into a block reason or None.

    Encapsulates the allow/ask/deny branching that is repeated for each
    rule source (external_directory, tool_policy, permission rules).
    Returns:
    - ``None`` when the decision is None or allows the call
    - a denial reason when the decision denies
    - the formatted ask-message when the decision is ``ask`` and not
      pre-approved by the session
    """
    if decision is None or decision.allowed:
        return None
    if decision.action == "ask":
        blocked = _decision_with_approval(decision, tool_name, args, session_key=session_key)
        if blocked is None:
            return None
        return _format_ask_message(blocked)
    return decision.reason


def _external_directory_block_or_none(
    tool_name: str,
    args: dict[str, Any],
    workspace: Path,
    *,
    session_key: str,
) -> str | None:
    """Apply external_directory rules for path-tools; ``None`` if N/A or allowed."""
    path_val = _resolve_path_arg(args)
    if not path_val or tool_name not in _PATH_TOOLS:
        return None
    ext = evaluate_external_directory(
        path_val,
        workspace=workspace,
        for_write=tool_name in ("write_file", "patch", "delete_file"),
    )
    return _apply_decision_or_none(
        ext, tool_name, args, session_key=session_key,
    )


def check_project_permission_block(
    tool_name: str,
    args: dict[str, Any],
) -> str | None:
    """Return error message when denied; None if allowed or no rule."""
    workspace = _current_workspace()
    if workspace is None:
        logger.warning(
            "check_project_permission_block: no workspace resolved, "
            "allowing %s (consider setting a project)",
            tool_name,
        )
        return None

    session_key = _current_session_key()

    bl = evaluate_security_blacklist(tool_name, args, workspace=workspace)
    if bl is not None and not bl.allowed:
        return bl.reason

    exp_block = _experiment_block_or_fail_closed(tool_name, args, workspace)
    if exp_block:
        return exp_block

    step_block = _workflow_step_block_or_fail_closed(tool_name, workspace)
    if step_block:
        return step_block

    ext_block = _external_directory_block_or_none(
        tool_name, args, workspace, session_key=session_key,
    )
    if ext_block:
        return ext_block

    return _apply_decision_or_none(
        evaluate_tool_policy(tool_name, workspace=workspace),
        tool_name, args, session_key=session_key,
    ) or _apply_decision_or_none(
        evaluate_permission(tool_name, args, workspace=workspace),
        tool_name, args, session_key=session_key,
    )


def _format_ask_message(decision: PermissionDecision) -> str:
    perm = str(decision.permission or "rule")
    return (
        f"{decision.reason}（需 Owner：/批准一次 或 /始终允许 {perm}）"
    )
