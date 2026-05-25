"""Load sub-agent definitions from ``.butler/agents/*.md`` (OpenHands subset)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


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
    try:
        import yaml

        loaded = yaml.safe_load(m.group(1))
        if isinstance(loaded, dict):
            meta = loaded
    except Exception:
        pass
    body = str(m.group(2) or "").strip()
    return meta, body


def load_agent_md(workspace: Path, name: str) -> AgentMdDef | None:
    key = str(name or "").strip().replace("_agent", "")
    if not key:
        return None
    base = Path(workspace).expanduser().resolve() / ".butler" / "agents"
    for candidate in (f"{key}.md", f"{key}_agent.md"):
        path = base / candidate
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.debug("agent md read %s: %s", path, exc)
            return None
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
    return None


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
