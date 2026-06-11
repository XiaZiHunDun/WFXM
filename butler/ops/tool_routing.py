"""Delegate vs direct-tool routing analysis for production turns (phase 4)."""

from __future__ import annotations

import re
from typing import Any

from butler.ops.eval_scoring import ScoreResult

_DEV_ACTION_RE = re.compile(
    r"(修复|修改|改写|重构|实现|添加|删除|创建|编写|改一下|修一下|"
    r"fix|patch|refactor|implement|add\s+\w+|delete|write|create|run\s+test|pytest)",
    re.IGNORECASE,
)
_READ_ONLY_RE = re.compile(
    r"(什么|哪些|列出|查看|状态|进度|怎么样|多少|"
    r"list|show|status|what|how many|overview|诊断)",
    re.IGNORECASE,
)
_DIRECT_DEV_TOOLS = frozenset({
    "terminal",
    "write_file",
    "apply_patch",
    "run_command",
    "execute_code",
    "edit_file",
})
_READONLY_TOOLS = frozenset({
    "read_file",
    "grep",
    "list_dir",
    "search",
    "memory_search",
    "switch_project",
    "list_projects",
    "get_project_status",
    "project_overview",
})


def expects_delegate_task(user_text: str) -> bool:
    """Heuristic: user message looks like a dev/file-edit task."""
    text = (user_text or "").strip()
    if not text:
        return False
    if _READ_ONLY_RE.search(text) and not _DEV_ACTION_RE.search(text):
        return False
    if "delegate" in text.lower() or "委派" in text or "交给开发" in text:
        return True
    return bool(_DEV_ACTION_RE.search(text))


def detect_routing_antipatterns(
    user_text: str,
    tools_used: list[str] | None,
) -> list[str]:
    """Return human-readable anti-pattern codes."""
    tools = [str(t).strip().lower() for t in (tools_used or []) if t]
    issues: list[str] = []
    if not expects_delegate_task(user_text):
        return issues
    has_delegate = "delegate_task" in tools
    direct = [t for t in tools if t in _DIRECT_DEV_TOOLS]
    if direct and not has_delegate:
        issues.append(f"delegate_miss:used_{direct[0]}_without_delegate")
    if has_delegate and direct:
        issues.append("delegate_mix:delegate_and_direct_dev_tools")
    return issues


def score_runtime_tool_routing(
    user_text: str,
    tools_used: list[str] | None,
) -> ScoreResult:
    """Score production tool routing without golden labels."""
    tools = [str(t).strip().lower() for t in (tools_used or []) if t]
    antipatterns = detect_routing_antipatterns(user_text, tools)
    expects = expects_delegate_task(user_text)
    has_delegate = "delegate_task" in tools
    direct = [t for t in tools if t in _DIRECT_DEV_TOOLS]

    if not tools:
        score = 0.55 if expects else 1.0
        comment = "no tools used" + ("; expected delegate" if expects else "")
    elif expects:
        if has_delegate and not direct:
            score = 1.0
            comment = "delegate used for dev-like task"
        elif direct and not has_delegate:
            score = 0.15
            comment = antipatterns[0] if antipatterns else "delegate_miss"
        elif has_delegate and direct:
            score = 0.55
            comment = "delegate_mix"
        else:
            score = 0.65
            comment = "dev-like task; weak routing"
    else:
        if has_delegate and len(tools) == 1:
            score = 0.75
            comment = "delegate on non-dev query"
        elif all(t in _READONLY_TOOLS for t in tools):
            score = 1.0
            comment = "read-only tools"
        else:
            penalty = 0.05 * len([t for t in tools if t not in _READONLY_TOOLS])
            score = max(0.7, 1.0 - penalty)
            comment = f"non-dev task; {len(tools)} tools"

    return ScoreResult(
        dimension="tool_selection",
        score=score,
        details={
            "expects_delegate": expects,
            "tools": tools,
            "antipatterns": antipatterns,
            "has_delegate": has_delegate,
            "direct_dev_tools": direct,
        },
        comment=comment,
    )


def score_delegate_routing(
    user_text: str,
    tools_used: list[str] | None,
) -> ScoreResult:
    """Dedicated delegate routing dimension (alias for dashboards)."""
    base = score_runtime_tool_routing(user_text, tools_used)
    return ScoreResult(
        dimension="delegate_routing",
        score=base.score,
        details=base.details,
        comment=base.comment,
    )


def routing_hint_from_overrides() -> str:
    """Optional prompt hint when hard feedback enabled delegate routing strict mode."""
    try:
        from butler.ops.eval_config_overrides import delegate_routing_hint_enabled

        if not delegate_routing_hint_enabled():
            return ""
    except Exception:
        return ""
    return (
        "[Eval Routing] Dev/file-edit requests should use delegate_task (dev role); "
        "avoid terminal or write_file for code changes unless user explicitly asks."
    )


__all__ = [
    "detect_routing_antipatterns",
    "expects_delegate_task",
    "routing_hint_from_overrides",
    "score_delegate_routing",
    "score_runtime_tool_routing",
]
