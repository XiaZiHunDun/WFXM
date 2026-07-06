"""Load sub-agent definitions from ``.butler/agents/*.md`` (OpenHands subset)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

# Sprint 22-4 PERF-21-B-3: mtime+size-keyed cache for agent md files.
# Mirrors hooks/loader (Sprint 21-3) + workflows/loader (Sprint 22-3) pattern.
# load_agent_md is called from merge_agent_md_into_context (line 91),
# which delegate_impl.py:324 invokes per message — without cache, each
# delegate incurs a disk read + frontmatter parse.
# Key: (str(workspace), str(name), str(path), mtime_ns, size) — auto-invalidates
# on file modification. Failed loads (OSError → None) are NOT cached to
# avoid poisoning subsequent reads.
_FILE_CACHE: dict[tuple[str, str, str, int, int], AgentMdDef] = {}


@dataclass
class AgentMdDef:
    name: str
    description: str = ""
    system_prompt: str = ""
    tools: list[str] | None = None
    triggers: list[str] = field(default_factory=list)
    permission_mode: str = ""


def _parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    text = str(raw or "").strip()
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta: dict[str, Any] = {}
    from butler.agents_md_ops import parse_yaml_frontmatter_safe

    loaded = parse_yaml_frontmatter_safe(m.group(1))
    if loaded is not None:
        meta = loaded
    body = str(m.group(2) or "").strip()
    return meta, body


def load_agent_md(workspace: Path, name: str) -> AgentMdDef | None:
    key = str(name or "").strip().replace("_agent", "")
    if not key:
        return None
    base = Path(workspace).expanduser().resolve() / ".butler" / "agents"
    ws_key = str(workspace)
    for candidate in (f"{key}.md", f"{key}_agent.md"):
        path = base / candidate
        if not path.is_file():
            continue
        try:
            st = path.stat()
        except OSError as exc:
            logger.debug("agent md stat %s: %s", path, exc)
            continue
        cache_key = (ws_key, key, str(path), st.st_mtime_ns, st.st_size)
        cached = _FILE_CACHE.get(cache_key)
        if cached is not None:
            return cached
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.debug("agent md read %s: %s", path, exc)
            return None
        agent = _parse_agent_md(key, raw)
        if agent is not None:
            _FILE_CACHE[cache_key] = agent
        return agent
    return None


def _parse_agent_md(key: str, raw: str) -> AgentMdDef | None:
    """Parse a raw agent md body into AgentMdDef. No I/O, no cache."""
    meta, body = _parse_frontmatter(raw)
    tools_raw = meta.get("tools")
    tools = None
    if isinstance(tools_raw, list):
        tools = [str(t).strip() for t in tools_raw if str(t).strip()]
    triggers_raw = meta.get("triggers")
    triggers: list[str] = []
    if isinstance(triggers_raw, list):
        triggers = [str(t).strip() for t in triggers_raw if str(t).strip()]
    elif isinstance(triggers_raw, str) and triggers_raw.strip():
        triggers = [triggers_raw.strip()]
    return AgentMdDef(
        name=key,
        description=str(meta.get("description") or "")[:500],
        system_prompt=body,
        tools=tools,
        triggers=triggers,
        permission_mode=str(meta.get("permission_mode") or "")[:32],
    )


def list_agent_md_names(workspace: Path) -> list[str]:
    base = Path(workspace).expanduser().resolve() / ".butler" / "agents"
    if not base.is_dir():
        return []
    out: list[str] = []
    for path in sorted(base.glob("*.md")):
        if path.is_file():
            out.append(path.stem)
    return out


def merge_agent_md_into_context(
    workspace: Path | None,
    role: str,
    context: str,
) -> str:
    if workspace is None:
        return context
    agent = load_agent_md(workspace, role)
    if agent is None or not agent.system_prompt.strip():
        return context
    block = f"## 子代理定义（.butler/agents/{agent.name}.md）\n{agent.system_prompt.strip()}"
    if agent.description:
        block = f"## 子代理：{agent.description}\n\n{agent.system_prompt.strip()}"
    base = str(context or "").strip()
    if base:
        return f"{base}\n\n{block}"
    return block


__all__ = [
    "AgentMdDef",
    "list_agent_md_names",
    "load_agent_md",
    "merge_agent_md_into_context",
]
