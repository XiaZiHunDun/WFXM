"""Execute shell hooks around tool dispatch (Claude Code stdin JSON protocol)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from butler.hooks.loader import HookRule, load_hooks_config, match_hook_query, match_tool

logger = logging.getLogger(__name__)


@dataclass
class UserPromptSubmitResult:
    blocked: bool = False
    block_message: str = ""
    additional_context: list[str] = field(default_factory=list)
    prevent_continuation: bool = False
    stop_message: str = ""


@dataclass
class StopHookResult:
    additional_context: list[str] = field(default_factory=list)
    blocked: bool = False
    block_message: str = ""
    decision: str = "continue"


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


def _session_key_from_payload(payload: dict[str, Any]) -> str:
    sk = str(payload.get("session_key") or "").strip()
    if sk:
        return sk
    try:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip()
    except Exception:
        return ""


def _collect_additional_context(specific: dict[str, Any], stdout: str) -> list[str]:
    out: list[str] = []
    ctx = specific.get("additionalContext") or specific.get("additional_context")
    if isinstance(ctx, list):
        for item in ctx:
            if str(item).strip():
                out.append(str(item).strip()[:4000])
    elif isinstance(ctx, str) and ctx.strip():
        out.append(ctx.strip()[:4000])
    elif stdout.strip() and not specific:
        out.append(stdout.strip()[:4000])
    return out


def _parse_hook_stdout(stdout: str, event: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    specific = data.get("hookSpecificOutput") or data.get("hook_specific_output")
    if not isinstance(specific, dict):
        return {}
    name = specific.get("hookEventName") or specific.get("hook_event_name")
    if name and str(name) != event:
        return {}
    return specific


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


def run_user_prompt_submit_hooks(
    prompt: str,
    *,
    session_key: str = "",
    platform: str = "unknown",
) -> UserPromptSubmitResult:
    """Run UserPromptSubmit hooks before an LLM turn. Exit 2 blocks the prompt."""
    result = UserPromptSubmitResult()
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt,
        "session_key": session_key,
        "platform": platform,
    }
    for rule in _rules_for_event("UserPromptSubmit"):
        if not match_hook_query(rule.matcher, prompt):
            continue
        code, out, err = _run_hook(rule, payload)
        if code == 2:
            msg = (err or out or "UserPromptSubmit hook blocked prompt").strip()
            result.blocked = True
            result.block_message = msg[:2000] or "UserPromptSubmit hook blocked prompt"
            return result
        specific = _parse_hook_stdout(out, "UserPromptSubmit")
        result.additional_context.extend(_collect_additional_context(specific, out))
        if specific.get("preventContinuation") or specific.get("prevent_continuation"):
            result.prevent_continuation = True
            reason = str(
                specific.get("stopReason") or specific.get("stop_reason") or ""
            ).strip()
            if reason:
                result.stop_message = reason[:2000]
        if code not in (0, None) and (out or err):
            logger.warning(
                "UserPromptSubmit hook exit %s: %s", code, (err or out)[:200]
            )
    return result


def run_permission_denied_hooks(
    tool_name: str,
    args: dict[str, Any],
    reason: str,
    *,
    tool_use_id: str = "",
) -> str | None:
    """Run PermissionDenied hooks; return optional hint for the model (e.g. retry allowed)."""
    payload = {
        "hook_event_name": "PermissionDenied",
        "tool_name": tool_name,
        "tool_input": args,
        "tool_use_id": tool_use_id or uuid.uuid4().hex[:12],
        "reason": reason,
    }
    hints: list[str] = []
    for rule in _rules_for_event("PermissionDenied"):
        if not match_tool(rule.matcher, tool_name):
            continue
        code, out, err = _run_hook(rule, payload)
        specific = _parse_hook_stdout(out, "PermissionDenied")
        if specific.get("retry") is True:
            hints.append(
                "PermissionDenied hook: retry is allowed; you may retry this tool."
            )
        msg = (err or out or "").strip()
        if msg and code == 0:
            hints.append(msg[:1500])
        elif code not in (0, None) and msg:
            logger.info("PermissionDenied hook exit %s for %s: %s", code, tool_name, msg[:200])
    if not hints:
        return None
    return "\n".join(hints)


def run_session_start_hooks(*, source: str = "clear") -> None:
    """Run SessionStart hooks (e.g. after /新对话)."""
    payload = {
        "hook_event_name": "SessionStart",
        "source": source,
    }
    for rule in _rules_for_event("SessionStart"):
        code, out, err = _run_hook(rule, payload)
        if code not in (0, None) and (out or err):
            logger.info("SessionStart hook exit %s: %s", code, (err or out)[:200])


def run_session_end_hooks(
    *,
    reason: str = "end",
    session_key: str = "",
) -> None:
    """Run SessionEnd hooks when a conversation session is torn down."""
    payload = {
        "hook_event_name": "SessionEnd",
        "reason": reason,
        "session_key": session_key,
    }
    for rule in _rules_for_event("SessionEnd"):
        if not match_hook_query(rule.matcher, reason):
            continue
        code, out, err = _run_hook(rule, payload)
        if code not in (0, None) and (out or err):
            logger.info("SessionEnd hook exit %s: %s", code, (err or out)[:200])


def run_stop_hooks(
    *,
    status: str,
    last_assistant_message: str = "",
    session_key: str = "",
    iterations: int = 0,
    tool_calls: int = 0,
    elapsed_seconds: float = 0.0,
) -> StopHookResult:
    """Run Stop hooks after a single agent turn finishes."""
    result = StopHookResult()
    payload = {
        "hook_event_name": "Stop",
        "status": status,
        "stop_hook_active": True,
        "last_assistant_message": (last_assistant_message or "")[:4000],
        "session_key": session_key,
        "iterations": iterations,
        "tool_calls": tool_calls,
        "elapsed_seconds": round(float(elapsed_seconds), 3),
    }
    for rule in _rules_for_event("Stop"):
        if not match_hook_query(rule.matcher, status):
            continue
        code, out, err = _run_hook(rule, payload)
        if code == 2:
            result.blocked = True
            result.decision = "block"
            result.block_message = (err or out or "Stop hook blocked turn").strip()[:2000]
            return result
        specific = _parse_hook_stdout(out, "Stop")
        result.additional_context.extend(_collect_additional_context(specific, out))
        decision = str(
            specific.get("decision") or specific.get("stopDecision") or ""
        ).strip().lower()
        if decision == "block" or specific.get("block") is True:
            result.blocked = True
            result.decision = "block"
            msg = str(
                specific.get("systemMessage")
                or specific.get("system_message")
                or specific.get("message")
                or ""
            ).strip()
            if msg:
                result.block_message = msg[:2000]
        if code not in (0, None) and (out or err):
            logger.info("Stop hook exit %s: %s", code, (err or out)[:200])
    return result


def run_subagent_start_hooks(
    *,
    agent_type: str,
    agent_id: str,
    task_preview: str = "",
    task_id: str = "",
    session_key: str = "",
) -> list[str]:
    """Run SubagentStart hooks before a delegated agent loop; return context to inject."""
    contexts: list[str] = []
    payload = {
        "hook_event_name": "SubagentStart",
        "agent_type": agent_type,
        "agent_id": agent_id,
        "task_preview": (task_preview or "")[:500],
        "task_id": task_id,
        "session_key": session_key,
    }
    for rule in _rules_for_event("SubagentStart"):
        if not match_tool(rule.matcher, agent_type):
            continue
        code, out, err = _run_hook(rule, payload)
        specific = _parse_hook_stdout(out, "SubagentStart")
        contexts.extend(_collect_additional_context(specific, out))
        if code not in (0, None) and (out or err):
            logger.info(
                "SubagentStart hook exit %s for %s: %s",
                code,
                agent_type,
                (err or out)[:200],
            )
    return contexts


def run_subagent_stop_hooks(
    *,
    agent_type: str,
    agent_id: str,
    success: bool,
    task_id: str = "",
    session_key: str = "",
    summary_preview: str = "",
) -> None:
    """Run SubagentStop hooks after a delegated agent loop finishes."""
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": agent_type,
        "agent_id": agent_id,
        "success": success,
        "task_id": task_id,
        "session_key": session_key,
        "summary_preview": (summary_preview or "")[:500],
        "stop_hook_active": True,
    }
    for rule in _rules_for_event("SubagentStop"):
        if not match_tool(rule.matcher, agent_type):
            continue
        code, out, err = _run_hook(rule, payload)
        if code not in (0, None) and (out or err):
            logger.info(
                "SubagentStop hook exit %s for %s: %s",
                code,
                agent_type,
                (err or out)[:200],
            )


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
        code = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        preview = (stderr or stdout or "").strip()[:120]
        try:
            from butler.hooks.telemetry import record_hook_run

            record_hook_run(
                session_key=_session_key_from_payload(payload),
                event=str(payload.get("hook_event_name") or rule.event),
                exit_code=code,
                preview=preview,
            )
        except Exception:
            pass
        return code, stdout, stderr
    except subprocess.TimeoutExpired:
        try:
            from butler.hooks.telemetry import record_hook_run

            record_hook_run(
                session_key=_session_key_from_payload(payload),
                event=str(payload.get("hook_event_name") or rule.event),
                exit_code=None,
                preview="hook timed out",
            )
        except Exception:
            pass
        return None, "", "hook timed out"
    except Exception as exc:
        logger.warning("Hook command failed: %s", exc)
        try:
            from butler.hooks.telemetry import record_hook_run

            record_hook_run(
                session_key=_session_key_from_payload(payload),
                event=str(payload.get("hook_event_name") or rule.event),
                exit_code=None,
                preview=str(exc)[:120],
            )
        except Exception:
            pass
        return None, "", str(exc)
