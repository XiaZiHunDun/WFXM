"""Project-layer memory: architecture, decisions, code patterns, known issues.

Separated from butler memory because project concerns are different:
- Technical facts about THIS specific project
- Code patterns and conventions
- Architecture decisions and their rationale
- Known issues and tech debt

Storage: <project>/.butler/memory/
  MEMORY.md            — human-readable structured sections
  knowledge.db         — SQLite + FTS5 + triplets (reuses SemanticMemoryIndex)
  facts.json           — auto-extracted project facts (no LLM needed)
  PENDING_DECISIONS.md — decisions awaiting user approval
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from butler.core.project_manager import Project

logger = logging.getLogger(__name__)

_PROJECT_SECTIONS = (
    "架构与设计",
    "关键决策",
    "代码模式与约定",
    "已知问题",
    "当前状态",
)

_ROLE_SECTIONS: dict[str, list[str]] = {
    "dev_agent": ["架构与设计", "代码模式与约定", "当前状态"],
    "dev": ["架构与设计", "代码模式与约定", "当前状态"],
    "content_agent": ["当前状态", "已知问题"],
    "content": ["当前状态", "已知问题"],
    "review_agent": ["架构与设计", "关键决策", "代码模式与约定"],
    "review": ["架构与设计", "关键决策", "代码模式与约定"],
}

_DECISION_KEYWORDS = frozenset({
    "决定", "决策", "选择", "改为", "替换", "弃用", "废弃", "迁移",
    "重构", "重写", "升级", "降级", "切换", "采用", "放弃", "转向",
    "decided", "decision", "chose", "switch", "migrate", "replace",
    "deprecate", "adopt", "abandon",
})


class MarkdownMemory:
    """Structured Markdown memory with section-based organization."""

    def __init__(self, memory_dir: Path):
        self.memory_dir = memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = memory_dir / "MEMORY.md"
        self.pending_file = memory_dir / "PENDING_DECISIONS.md"
        if not self.index_file.exists():
            self._init_memory()

    def _init_memory(self) -> None:
        lines = [
            "# 项目记忆\n\n",
            f"> 创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n",
        ]
        for section in _PROJECT_SECTIONS:
            lines.append(f"## {section}\n\n")
        self.index_file.write_text("".join(lines), encoding="utf-8")

    def read(self) -> str:
        if self.index_file.exists():
            return self.index_file.read_text(encoding="utf-8")
        return ""

    def append(self, section: str, content: str) -> None:
        text = self.read()
        marker = f"## {section}"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"- [{timestamp}] {content}\n"

        if marker in text:
            idx = text.index(marker)
            end_of_line = text.index("\n", idx) + 1
            next_section = text.find("\n## ", end_of_line)
            insert_at = next_section if next_section != -1 else len(text)
            text = text[:insert_at] + entry + text[insert_at:]
        else:
            text += f"\n## {section}\n\n{entry}"
        self.index_file.write_text(text, encoding="utf-8")

    def get_sections(self, section_names: list[str] | None = None, max_chars: int = 3000) -> str:
        """Get specific sections from MEMORY.md."""
        text = self.read()
        if not text:
            return ""
        if section_names is None:
            return text[:max_chars]

        parts: list[str] = []
        total = 0
        for section in section_names:
            marker = f"## {section}"
            if marker not in text:
                continue
            idx = text.index(marker)
            next_section = text.find("\n## ", idx + len(marker))
            block = text[idx:next_section] if next_section != -1 else text[idx:]
            block = block.strip()
            if not block or block == marker:
                continue
            if total + len(block) > max_chars:
                remaining = max_chars - total
                if remaining > 50:
                    parts.append(block[:remaining] + "...")
                break
            parts.append(block)
            total += len(block)

        return "\n\n".join(parts)

    def classify_and_append(self, section: str, content: str) -> str:
        """Classify as fact or decision, route accordingly. Returns classification."""
        content_lower = content.lower()
        for kw in _DECISION_KEYWORDS:
            if kw in content_lower:
                self._append_pending(section, content)
                return "decision"
        self.append(section, content)
        return "fact"

    def _append_pending(self, section: str, content: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"- [{timestamp}] [{section}] {content}\n"
        existing = ""
        if self.pending_file.exists():
            existing = self.pending_file.read_text(encoding="utf-8")
        if not existing:
            existing = "# 待审核的决策记忆\n\n"
        existing += entry
        self.pending_file.write_text(existing, encoding="utf-8")

    def get_pending(self) -> list[dict]:
        if not self.pending_file.exists():
            return []
        text = self.pending_file.read_text(encoding="utf-8")
        results = []
        for line in text.splitlines():
            m = re.match(r'^- \[([^\]]+)\] \[([^\]]+)\] (.+)$', line)
            if m:
                results.append({"timestamp": m.group(1), "section": m.group(2), "content": m.group(3)})
        return results

    def approve_pending(self, indices: list[int] | None = None) -> int:
        pending = self.get_pending()
        if not pending:
            return 0
        to_approve = pending if indices is None else [pending[i] for i in indices if 0 <= i < len(pending)]
        for item in to_approve:
            self.append(item["section"], item["content"])
        if indices is None:
            self.pending_file.unlink(missing_ok=True)
        else:
            approved_set = {(item["timestamp"], item["content"]) for item in to_approve}
            lines = ["# 待审核的决策记忆\n\n"]
            for item in pending:
                if (item["timestamp"], item["content"]) not in approved_set:
                    lines.append(f"- [{item['timestamp']}] [{item['section']}] {item['content']}\n")
            self.pending_file.write_text("".join(lines), encoding="utf-8")
        return len(to_approve)


class ProjectFactsStore:
    """Auto-extracted project facts (no LLM needed)."""

    def __init__(self, facts_path: Path):
        self.path = facts_path
        self._facts: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._facts = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._facts = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._facts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def auto_extract(self, project_root: Path) -> dict:
        """Scan project files to extract facts without LLM."""
        facts: dict[str, Any] = {"extracted_at": time.time()}

        # Python
        pyproject = project_root / "pyproject.toml"
        if pyproject.exists():
            facts["build_system"] = "python"
            text = pyproject.read_text(encoding="utf-8", errors="replace")
            if "fastapi" in text.lower():
                facts.setdefault("frameworks", []).append("FastAPI")
            if "django" in text.lower():
                facts.setdefault("frameworks", []).append("Django")
            if "flask" in text.lower():
                facts.setdefault("frameworks", []).append("Flask")

        requirements = project_root / "requirements.txt"
        if requirements.exists():
            facts["build_system"] = facts.get("build_system", "python")
            deps = [l.split("==")[0].split(">=")[0].strip()
                    for l in requirements.read_text(encoding="utf-8", errors="replace").splitlines()
                    if l.strip() and not l.startswith("#")]
            facts["python_dependencies"] = deps[:30]

        # Node.js
        pkg_json = project_root / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
                facts["build_system"] = facts.get("build_system", "node")
                facts["node_dependencies"] = list(pkg.get("dependencies", {}).keys())[:30]
                if "react" in pkg.get("dependencies", {}):
                    facts.setdefault("frameworks", []).append("React")
                if "vue" in pkg.get("dependencies", {}):
                    facts.setdefault("frameworks", []).append("Vue")
                if "next" in pkg.get("dependencies", {}):
                    facts.setdefault("frameworks", []).append("Next.js")
            except (json.JSONDecodeError, OSError):
                pass

        # Go
        go_mod = project_root / "go.mod"
        if go_mod.exists():
            facts["build_system"] = facts.get("build_system", "go")

        # Directory structure
        top_dirs = sorted([
            d.name for d in project_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
               and d.name not in ("node_modules", "__pycache__", ".git", "venv", ".venv")
        ])[:20]
        facts["directory_structure"] = top_dirs

        # File counts
        py_count = len(list(project_root.rglob("*.py")))
        js_count = len(list(project_root.rglob("*.js"))) + len(list(project_root.rglob("*.ts")))
        facts["file_counts"] = {"python": py_count, "javascript_typescript": js_count}

        self._facts = facts
        self._save()
        return facts

    def get_facts(self) -> dict:
        return dict(self._facts)

    def format_for_prompt(self) -> str:
        if not self._facts:
            return ""
        parts: list[str] = []
        if "build_system" in self._facts:
            parts.append(f"构建系统: {self._facts['build_system']}")
        if "frameworks" in self._facts:
            parts.append(f"框架: {', '.join(self._facts['frameworks'])}")
        if "directory_structure" in self._facts:
            parts.append(f"目录: {', '.join(self._facts['directory_structure'][:10])}")
        return "\n".join(parts)


class ProjectMemory:
    """Project-layer memory: all technical knowledge about a specific project."""

    def __init__(self, project_workspace: Path):
        self.workspace = project_workspace
        mem_dir = project_workspace / ".butler" / "memory"
        self.markdown = MarkdownMemory(mem_dir)
        self.facts = ProjectFactsStore(mem_dir / "facts.json")
        self._knowledge = None  # lazy SemanticMemoryIndex

    @classmethod
    def for_project(cls, project: Project) -> ProjectMemory:
        return cls(project.workspace)

    @classmethod
    def for_project_name(cls, project_name: str) -> ProjectMemory | None:
        from butler.core.project_manager import project_manager
        proj = project_manager.get_project(project_name)
        if proj:
            return cls.for_project(proj)
        return None

    @property
    def knowledge(self):
        if self._knowledge is None:
            from butler.storage.memory_store import SemanticMemoryIndex
            db_path = self.workspace / ".butler" / "memory" / "knowledge.db"
            self._knowledge = SemanticMemoryIndex(db_path)
        return self._knowledge

    def get_context_for_agent(self, role: str, task: str = "", max_tokens: int = 2000) -> str:
        """Return role-appropriate memory context for an agent."""
        parts: list[str] = []

        # Facts summary (always included, lightweight)
        facts_text = self.facts.format_for_prompt()
        if facts_text:
            parts.append(f"## 项目概况\n{facts_text}")

        # Role-specific sections from MEMORY.md
        sections = _ROLE_SECTIONS.get(role, list(_PROJECT_SECTIONS))
        section_text = self.markdown.get_sections(sections, max_chars=max_tokens)
        if section_text:
            parts.append(section_text)

        # Task-relevant knowledge (FTS5 search if task provided)
        if task:
            try:
                relevant = self.knowledge.search_ranked(task, max_items=5)
                if relevant:
                    knowledge_lines = [f"- {r[2]}" for r in relevant[:5]]
                    parts.append("## 相关知识\n" + "\n".join(knowledge_lines))
            except Exception:
                pass

        if not parts:
            return "(暂无项目记忆)"
        return "\n\n".join(parts)

    def get_full_context(self, max_lines: int = 50) -> str:
        """Get full memory context (for butler system prompt)."""
        text = self.markdown.read()
        lines = text.splitlines()
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines.append("... (更多记忆已截断)")
        return "\n".join(lines)

    def append(self, section: str, content: str) -> None:
        self.markdown.append(section, content)

    def append_with_classification(self, section: str, content: str) -> str:
        return self.markdown.classify_and_append(section, content)

    def add_triplet(self, subject: str, relation: str, obj: str) -> None:
        self.knowledge.add_triplet(subject, relation, obj)

    def query_triplets(self, subject: str = "", relation: str = "", obj: str = "") -> list:
        return self.knowledge.query_triplets(subject=subject, relation=relation, object=obj)

    def get_pending_decisions(self) -> list[dict]:
        return self.markdown.get_pending()

    def approve_pending(self, indices: list[int] | None = None) -> int:
        return self.markdown.approve_pending(indices)

    def auto_extract_facts(self) -> dict:
        return self.facts.auto_extract(self.workspace)
