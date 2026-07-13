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

# Sprint 21-3 PERF-21-B-1: mtime+size-keyed cache for parsed hook rules.
# Mirrors skill_manager._full_cache (Sprint 20-4) and skill_manager
# _metadata_cache. Keyed by (str(path), mtime_ns, size) so the cache
# auto-invalidates on file modification.
_FILE_CACHE: dict[tuple[str, int, int], list["HookRule"]] = {}


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
    """Merge hooks: ``~/.butler/config.yaml`` → ``~/.butler/.butler/hooks.yaml`` → project hooks (``config/hooks.yaml`` tracked first, then ``.butler/hooks.yaml`` runtime override)."""
    from butler.hooks.loader_ops import load_butler_global_hooks_safe

    rules: list[HookRule] = list(load_butler_global_hooks_safe(_load_file))

    if workspace is not None:
        # R3-2: project hooks are loaded here; tool writes to this path are
        # blocked in path_safety._hooks_config_write_error (persistent RCE).
        # 2026-07-13: P1#4 — also load from tracked config/hooks.yaml
        # (gitignored .butler/ cannot host checked-in hook config).
        config_tracked = Path(workspace) / "config" / "hooks.yaml"
        rules.extend(_load_file(config_tracked))
        rules.extend(_load_file(Path(workspace) / ".butler" / "hooks.yaml"))
    return rules


def _load_file(path: Path) -> list[HookRule]:
    if not path.is_file():
        return []
    try:
        st = path.stat()
    except OSError as exc:
        logger.debug("Could not stat %s: %s", path, exc)
        return []
    key = (str(path), st.st_mtime_ns, st.st_size)
    cached = _FILE_CACHE.get(key)
    if cached is not None:
        return list(cached)
    from butler.hooks.loader_ops import parse_hooks_yaml_dict_safe

    data = parse_hooks_yaml_dict_safe(path)
    if data is None:
        return []
    hooks = _hooks_dict_from_data(data)
    if hooks is None:
        return []
    out: list[HookRule] = []
    for event in _HOOK_EVENTS:
        out.extend(_parse_rules(hooks.get(event), event))
    _FILE_CACHE[key] = out
    return list(out)


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
        except re.error as exc:
            # Sprint 22-5 TEST-21-C-1: invalid regex fail-loud. Mirror
            # `butler/permissions/rules.py:280` (security_blacklist regex
            # warning). Without the log, a typo in hooks.yaml matcher
            # silently makes the hook never fire — user has no idea.
            logger.warning(
                "hook matcher regex invalid (matcher=%r): %s",
                matcher, exc,
            )
            return False
    return pat in query
