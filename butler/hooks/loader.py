"""Load hook definitions from config.yaml, hooks.yaml, and project overrides."""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_HOOK_EVENTS = (
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PermissionDenied",
    "UserPromptSubmit",
    "PreCompact",
    "PostCompact",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "SubagentStart",
    "SubagentStop",
)


@dataclass(frozen=True)
class HookRule:
    event: str
    matcher: str
    command: str
    cwd: str = ""


def _parse_rules(raw: Any, event: str) -> list[HookRule]:
    if not isinstance(raw, list):
        return []
    rules: list[HookRule] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cmd = str(item.get("command") or "").strip()
        if not cmd:
            continue
        rules.append(
            HookRule(
                event=event,
                matcher=str(item.get("matcher") or item.get("tool") or "*").strip() or "*",
                command=cmd,
                cwd=str(item.get("cwd") or "").strip(),
            )
        )
    return rules


def _hooks_dict_from_data(data: dict[str, Any]) -> dict[str, Any] | None:
    hooks = data.get("hooks")
    if isinstance(hooks, dict):
        return hooks
    return None


def load_hooks_config(workspace: Path | None = None) -> list[HookRule]:
    """Merge hooks: ``~/.butler/config.yaml`` → ``~/.butler/.butler/hooks.yaml`` → project."""
    rules: list[HookRule] = []
    try:
        from butler.config import get_butler_settings

        settings = get_butler_settings()
        cfg_path = settings.config_yaml_path
        if cfg_path.is_file():
            rules.extend(_load_file(cfg_path))
        rules.extend(_load_file(settings.butler_home / ".butler" / "hooks.yaml"))
    except Exception as exc:
        logger.debug("Global hooks load skipped: %s", exc)

    if workspace is not None:
        rules.extend(_load_file(Path(workspace) / ".butler" / "hooks.yaml"))
    return rules


def _load_file(path: Path) -> list[HookRule]:
    if not path.is_file():
        return []
    try:
        import yaml
    except ImportError:
        logger.debug("PyYAML not installed; skipping %s", path)
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load hooks %s: %s", path, exc)
        return []
    if not isinstance(data, dict):
        return []
    hooks = _hooks_dict_from_data(data)
    if hooks is None:
        return []
    out: list[HookRule] = []
    for event in _HOOK_EVENTS:
        out.extend(_parse_rules(hooks.get(event), event))
    return out


def match_tool(matcher: str, tool_name: str) -> bool:
    pat = (matcher or "*").strip()
    if pat in ("*", ""):
        return True
    if "|" in pat:
        return any(match_tool(part.strip(), tool_name) for part in pat.split("|"))
    return fnmatch.fnmatch(tool_name, pat)


def match_hook_query(matcher: str, query: str) -> bool:
    """Match prompts or other free-text hook targets (substring or ``re:`` pattern)."""
    pat = (matcher or "*").strip()
    if pat in ("*", ""):
        return True
    if "|" in pat:
        return any(match_hook_query(part.strip(), query) for part in pat.split("|"))
    if pat.startswith("re:"):
        import re

        try:
            return bool(re.search(pat[3:], query, re.DOTALL))
        except re.error:
            return False
    return pat in query
