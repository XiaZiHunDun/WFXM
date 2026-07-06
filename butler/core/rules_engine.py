"""Workspace rules walk-up with glob triggers (OMO rules-engine lite)."""

from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_RULE_DIRS = (".butler/rules", ".claude/rules")
_RULE_EXTENSIONS = (".md", ".txt")


def rules_engine_enabled() -> bool:
    from butler.env_parse import env_truthy

    return bool(env_truthy("BUTLER_RULES_ENGINE", default=True))


def max_chars() -> int:
    try:
        from butler.env_parse import int_env

        return int(int_env("BUTLER_RULES_MAX_CHARS", 6000, min=500))
    except ValueError:
        return 6000


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    header = text[4:end]
    body = text[end + 5 :]
    meta: dict[str, str] = {}
    for line in header.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    return meta, body


def _glob_match(pattern: str, rel_path: str) -> bool:
    pat = pattern.strip().replace("\\", "/")
    rel = rel_path.replace("\\", "/")
    if not pat:
        return False
    return fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, f"**/{pat}")


def _collect_rule_files(workspace: Path) -> list[Path]:
    found: list[Path] = []
    for sub in _RULE_DIRS:
        base = workspace / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix.lower() in _RULE_EXTENSIONS:
                found.append(path)
    return found


def resolve_rules_for_path(
    trigger_path: Path,
    *,
    workspace_root: Path | None = None,
) -> str:
    """Return concatenated rule bodies applicable to trigger_path."""
    if not rules_engine_enabled():
        return ""
    try:
        resolved = trigger_path.resolve()
    except OSError:
        return ""
    workspace = workspace_root.resolve() if workspace_root else None
    if workspace is None:
        workspace = resolved.parent
        for _ in range(32):
            if any((workspace / d).is_dir() for d in _RULE_DIRS):
                break
            if workspace.parent == workspace:
                break
            workspace = workspace.parent

    rel = ""
    try:
        rel = str(resolved.relative_to(workspace)).replace("\\", "/")
    except ValueError:
        rel = resolved.name

    candidates: list[tuple[float, str, str]] = []
    for rule_file in _collect_rule_files(workspace):
        try:
            raw = rule_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        meta, body = _parse_frontmatter(raw)
        always = meta.get("alwaysapply", meta.get("always_apply", "")).lower() in (
            "true",
            "1",
            "yes",
        )
        globs = meta.get("globs", meta.get("glob", ""))
        matched = always
        if not matched and globs:
            for pat in globs.replace(",", " ").split():
                if _glob_match(pat, rel):
                    matched = True
                    break
        if not matched:
            continue
        try:
            depth = len(rule_file.relative_to(workspace).parts)
        except ValueError:
            depth = 99
        priority = int(meta.get("priority", "0") or "0")
        title = meta.get("title") or rule_file.stem
        candidates.append((depth - priority * 0.01, title, body.strip()))

    if not candidates:
        return ""

    candidates.sort(key=lambda x: x[0])
    parts: list[str] = []
    total = 0
    cap = max_chars()
    for _score, title, body in candidates:
        block = f"### Rule: {title}\n{body}"
        if total + len(block) > cap:
            remain = cap - total
            if remain > 200:
                parts.append(block[:remain] + "\n…[truncated]")
            break
        parts.append(block)
        total += len(block)

    if not parts:
        return ""
    return "## Workspace rules (triggered)\n" + "\n\n".join(parts)
