"""Execute shell hooks around tool dispatch (Claude Code stdin JSON protocol)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from butler.hooks.loader import HookRule, load_hooks_config, match_tool

logger = logging.getLogger(__name__)


def _resolve_workspace() -> Path | None:
    try:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        if orch is None:
            return None
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            return None
        from butler.execution_context import get_current_session_key

        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            return None
        return Path(proj.workspace)
    except Exception:
        return None


def _rules_for_event(event: str) -> list[HookRule]:
    return [r for r in load_hooks_config(_resolve_workspace()) if r.event == event]


def _hook_payload(
    event: str,
    tool_name: str,
    args: dict[str, Any],
    *,
    result: str = "",
    failed: bool = False,
    error: str = "",
) -> dict[str, Any]:
    if event == "PreToolUse":
        return {
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": args,
        }
    if event == "PostToolUseFailure":
        return {
            "hook_event_name": "PostToolUseFailure",
            "tool_name": tool_name,
            "tool_input": args,
            "tool_response": result,
            "error": error or result,
            "is_interrupt": False,
        }
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": args,
        "tool_response": result,
    }


def run_pre_tool_hooks(tool_name: str, args: dict[str, Any]) -> str | None:
    """Run PreToolUse hooks. Return error string to block tool, or None to continue."""
    for rule in _rules_for_event("PreToolUse"):
        if not match_tool(rule.matcher, tool_name):
            continue
        code, out, err = _run_hook(
            rule,
            _hook_payload("PreToolUse", tool_name, args),
        )
        if code == 2:
            msg = (err or out or "Hook blocked tool execution").strip()
            return msg[:2000] or "Hook blocked tool execution"
        if code != 0 and code is not None:
            logger.warning("PreToolUse hook exit %s for %s: %s", code, tool_name, err or out)
    return None


def run_post_tool_hooks(
    tool_name: str,
    args: dict[str, Any],
    result: str,
    *,
    failed: bool = False,
) -> str:
    """Run PostToolUse hooks; optional stderr/context appended to tool result."""
    event = "PostToolUseFailure" if failed else "PostToolUse"
    extra: list[str] = []
    payload = _hook_payload(
        event,
        tool_name,
        args,
        result=result,
        failed=failed,
    )
    for rule in _rules_for_event(event):
        if not match_tool(rule.matcher, tool_name):
            continue
        code, out, err = _run_hook(rule, payload)
        if code == 2 and (out or err):
            extra.append((out or err).strip()[:1500])
        elif out and code == 0:
            extra.append(out.strip()[:800])
    if not extra:
        return result
    block = "\n".join(extra)
    try:
        parsed = json.loads(result)
        if isinstance(parsed, dict):
            parsed = dict(parsed)
            parsed["hook_context"] = block
            return json.dumps(parsed, ensure_ascii=False)
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return result + "\n\n[hook]\n" + block


def _run_hook(
    rule: HookRule,
    payload: dict[str, Any],
) -> tuple[int | None, str, str]:
    cwd = rule.cwd or os.getcwd()
    stdin_json = json.dumps(payload, ensure_ascii=False)
    env = {
        **os.environ,
        "BUTLER_HOOK_EVENT": str(payload.get("hook_event_name") or rule.event),
        "BUTLER_HOOK_TOOL": str(payload.get("tool_name") or ""),
        "BUTLER_HOOK_INPUT": stdin_json[:8000],
    }
    try:
        proc = subprocess.run(
            rule.command,
            shell=True,
            cwd=cwd,
            input=stdin_json,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return None, "", "hook timed out"
    except Exception as exc:
        logger.warning("Hook command failed: %s", exc)
        return None, "", str(exc)
