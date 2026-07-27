from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from .facts_store import ProjectFactsStore
from .markdown_memory import MarkdownMemory
from .role_sections import sections_for_agent_role


class ProjectMemory:
    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir).resolve()
        mem_dir = self.project_dir / ".butler" / "memory"
        mem_dir.mkdir(parents=True, exist_ok=True)
        self.markdown = MarkdownMemory(mem_dir / "MEMORY.md")
        self.facts = ProjectFactsStore(mem_dir / "facts.json")

    @classmethod
    def for_project(cls, project: Path | str) -> ProjectMemory:
        return cls(Path(project))

    def refresh_facts(self) -> dict[str, Any]:
        return self.facts.refresh(self.project_dir)

    def facts_for_prefetch(self, *, max_chars: int = 400) -> str:
        text = self.facts.format_for_prompt()
        if not text:
            return ""
        cap = max(0, int(max_chars))
        if cap and len(text) > cap:
            return text[:cap] + "\n…(项目 facts 已截断)"
        return text

    def get_context_for_agent(self, role: str) -> str:
        sections = sections_for_agent_role(role)

        parts: list[str] = []
        ft = self.facts.format_for_prompt()
        if ft:
            parts.append(f"## Project facts (auto)\n{ft}")

        chunks: list[str] = []
        for name in sections:
            block = self.markdown.get_section(name)
            if block:
                chunks.append(f"## {name}\n{block}")

        if chunks:
            parts.append("\n\n".join(chunks))

        if not parts:
            return "(No project memory yet.)"
        return "\n\n".join(parts)

    def get_full_context(self, max_lines: int = 40) -> str:
        ft = self.facts.format_for_prompt()
        md = self.path_read_memory_file()
        lines_out: list[str] = []
        if ft:
            lines_out.append("### Auto-extracted facts")
            lines_out.extend(ft.splitlines())
            lines_out.append("")
        lines_out.append("### MEMORY.md (truncated)")
        md_lines = md.splitlines()
        if len(md_lines) <= max_lines:
            lines_out.extend(md_lines)
        else:
            lines_out.extend(md_lines[:max_lines])
            lines_out.append(f"... ({len(md_lines) - max_lines} more lines omitted)")
        return "\n".join(lines_out)

    def path_read_memory_file(self) -> str:
        p = self.markdown.path
        if not p.exists():
            return ""
        from butler.memory.memory_caps import truncate_memory_text
        text, _ = truncate_memory_text(p.read_text(encoding="utf-8"))
        return cast(str, text)