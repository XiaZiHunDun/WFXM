"""Project-level memory: markdown knowledge and auto-extracted facts."""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

_SECTION_ORDER = (
    "Architecture",
    "Decisions",
    "Patterns",
    "API",
    "Notes",
    "Pending",
)

_DECISION_KEYWORDS = frozenset(
    {
        "决定",
        "决策",
        "选择",
        "改为",
        "替换",
        "弃用",
        "废弃",
        "迁移",
        "重构",
        "升级",
        "降级",
        "切换",
        "采用",
        "放弃",
        "转向",
        "decided",
        "decision",
        "chose",
        "choose",
        "switch",
        "migrate",
        "migrating",
        "replace",
        "deprecate",
        "adopt",
        "abandon",
        "we should",
        "we will",
        "going to",
    }
)

_PENDING_UNCERTAIN = frozenset(
    {
        "maybe",
        "perhaps",
        "不确定",
        "待确认",
        "待定",
        "考虑",
        "possibly",
        "tbd",
        "wip",
    }
)

_ROLE_SECTIONS: dict[str, tuple[str, ...]] = {
    "dev": ("Architecture", "Patterns", "API", "Notes"),
    "developer": ("Architecture", "Patterns", "API", "Notes"),
    "impl": ("Architecture", "Patterns", "API"),
    "code": ("Architecture", "Patterns", "API"),
    "review": ("Architecture", "Decisions", "Patterns"),
    "reviewer": ("Architecture", "Decisions", "Patterns"),
    "plan": ("Architecture", "Decisions", "Notes"),
    "architect": ("Architecture", "Decisions", "Patterns", "API"),
    "default": ("Architecture", "Decisions", "Patterns", "API", "Notes"),
}

_PENDING_LINE_RE = re.compile(
    r"^-\s*\[PENDING\]\s*\[target:(?P<target>[^\]]+)\]\s*\[(?P<ts>[^\]]+)\]\s*(?P<body>.+)$"
)

# Chinese headers from legacy MEMORY.md / post_session → canonical sections
_SECTION_ALIASES: dict[str, str] = {
    "架构与设计": "Architecture",
    "架构": "Architecture",
    "设计": "Architecture",
    "关键决策": "Decisions",
    "决策": "Decisions",
    "代码模式与约定": "Patterns",
    "代码模式": "Patterns",
    "约定": "Patterns",
    "已知问题": "Notes",
    "问题": "Notes",
    "当前状态": "Notes",
    "状态": "Notes",
    "接口": "API",
}


def normalize_section_name(section: str) -> str:
    """Map legacy Chinese headers and aliases to canonical section names."""
    raw = (section or "Notes").strip()
    if raw in _SECTION_ORDER:
        return raw
    return _SECTION_ALIASES.get(raw, raw)


def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


class MarkdownMemory:
    """Structured MEMORY.md with fixed sections and an approval queue."""

    def __init__(self, memory_file: Path):
        self.path = Path(memory_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self._init_file()

    def _init_file(self) -> None:
        lines = [
            "# Project memory\n\n",
            f"> Created: {_now_ts()}\n\n",
        ]
        for name in _SECTION_ORDER:
            lines.append(f"## {name}\n\n")
        self.path.write_text("".join(lines), encoding="utf-8")

    def _read_unlocked(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def _write_unlocked(self, text: str) -> None:
        self.path.write_text(text, encoding="utf-8")

    @staticmethod
    def _auto_classify(content: str) -> str:
        lower = content.lower()
        if any(u in lower for u in _PENDING_UNCERTAIN):
            return "pending"
        for kw in _DECISION_KEYWORDS:
            if kw in lower:
                return "pending"
        return "fact"

    def append(
        self,
        section: str,
        content: str,
        classification: str = "auto",
    ) -> str:
        section = normalize_section_name(section)
        raw_cls = (classification or "auto").strip().lower()
        if raw_cls == "auto":
            cls_in = self._auto_classify(content)
            pending_from_auto = cls_in == "pending"
        else:
            cls_in = raw_cls
            pending_from_auto = False

        with self._lock:
            if cls_in == "fact":
                self._append_bullet_unlocked(section, content)
                return "fact"
            if cls_in == "decision":
                self._append_bullet_unlocked("Decisions", content)
                return "decision"
            if cls_in == "pending":
                if pending_from_auto:
                    tgt = "Decisions"
                else:
                    tgt = section.strip() or "Decisions"
                self._append_pending_unlocked(tgt, content)
                return "pending"
            self._append_bullet_unlocked(section, content)
            return "fact"

    def _append_bullet_unlocked(self, section: str, content: str) -> None:
        text = self._read_unlocked()
        marker = f"## {section}"
        ts = _now_ts()
        entry = f"- [{ts}] {content.strip()}\n"
        if marker not in text:
            text = text.rstrip() + f"\n\n{marker}\n\n{entry}"
            self._write_unlocked(text)
            return
        idx = text.index(marker)
        eol = text.index("\n", idx) + 1
        nxt = text.find("\n## ", eol)
        insert_at = nxt if nxt != -1 else len(text)
        text = text[:insert_at] + entry + text[insert_at:]
        self._write_unlocked(text)

    def _append_pending_unlocked(self, target_section: str, content: str) -> None:
        text = self._read_unlocked()
        marker = "## Pending"
        ts = _now_ts()
        tgt = target_section.strip() or "Decisions"
        entry = f"- [PENDING] [target:{tgt}] [{ts}] {content.strip()}\n"
        if marker not in text:
            text = text.rstrip() + f"\n\n{marker}\n\n{entry}"
            self._write_unlocked(text)
            return
        idx = text.index(marker)
        eol = text.index("\n", idx) + 1
        nxt = text.find("\n## ", eol)
        insert_at = nxt if nxt != -1 else len(text)
        text = text[:insert_at] + entry + text[insert_at:]
        self._write_unlocked(text)

    def _extract_section(self, text: str, name: str) -> str:
        marker = f"## {name}"
        if marker not in text:
            return ""
        start = text.index(marker) + len(marker)
        nxt = text.find("\n## ", start)
        block = text[start:nxt] if nxt != -1 else text[start:]
        return block.strip()

    def get_section(self, name: str) -> str:
        with self._lock:
            return self._extract_section(self._read_unlocked(), name)

    def get_all_sections(self) -> dict[str, str]:
        with self._lock:
            text = self._read_unlocked()
        return {name: self._extract_section(text, name) for name in _SECTION_ORDER}

    def list_pending(self) -> list[dict[str, str]]:
        raw = self.get_section("Pending")
        if not raw:
            return []
        out: list[dict[str, str]] = []
        for line in raw.splitlines():
            m = _PENDING_LINE_RE.match(line.strip())
            if not m:
                continue
            out.append(
                {
                    "target": m.group("target"),
                    "timestamp": m.group("ts"),
                    "content": m.group("body"),
                    "line": line.strip(),
                }
            )
        return out

    def approve_pending(self, idx: int) -> bool:
        pending = self.list_pending()
        if not (0 <= idx < len(pending)):
            return False
        item = pending[idx]
        target = item["target"]
        body = item["content"]
        line = item["line"]
        with self._lock:
            text = self._read_unlocked()
            pend_block = self._extract_section(text, "Pending")
            if not any(ln.strip() == line.strip() for ln in pend_block.splitlines()):
                return False
            new_pend_lines = []
            removed = False
            for ln in pend_block.splitlines():
                if not removed and ln.strip() == line.strip():
                    removed = True
                    continue
                new_pend_lines.append(ln)
            new_pend = "\n".join(new_pend_lines).strip()
            self._replace_section_body_unlocked(text, "Pending", new_pend)
            self._append_bullet_unlocked(target, body)
        return True

    def approve_all(self) -> int:
        count = 0
        while True:
            pend = self.list_pending()
            if not pend:
                break
            if not self.approve_pending(0):
                break
            count += 1
        return count

    def _replace_section_body_unlocked(self, text: str, section: str, new_body: str) -> None:
        marker = f"## {section}"
        if marker not in text:
            self._write_unlocked(text.rstrip() + f"\n\n{marker}\n\n{new_body}\n")
            return
        idx = text.index(marker)
        eol = text.index("\n", idx) + 1
        nxt = text.find("\n## ", eol)
        if nxt == -1:
            new_text = text[:eol] + (new_body + "\n" if new_body else "\n")
        else:
            spacer = "\n\n" if new_body else ""
            mid = new_body + spacer if new_body else "\n"
            new_text = text[:eol] + mid + text[nxt:]
        self._write_unlocked(new_text.rstrip() + "\n")


class ProjectFactsStore:
    """Facts inferred from repository files (no LLM)."""

    def __init__(self, facts_path: Path):
        self.path = Path(facts_path)
        self._facts: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        with self._lock:
            if self.path.exists():
                try:
                    self._facts = json.loads(self.path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    self._facts = {}
            else:
                self._facts = {}

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._facts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def auto_extract(self, project_dir: Path) -> dict[str, Any]:
        root = Path(project_dir).resolve()
        facts: dict[str, Any] = {"extracted_at": time.time()}

        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            facts["build_system"] = "python"
            ptext = pyproject.read_text(encoding="utf-8", errors="replace").lower()
            if "fastapi" in ptext:
                facts.setdefault("frameworks", []).append("FastAPI")
            if "django" in ptext:
                facts.setdefault("frameworks", []).append("Django")
            if "flask" in ptext:
                facts.setdefault("frameworks", []).append("Flask")

        requirements = root / "requirements.txt"
        if requirements.exists():
            facts["build_system"] = facts.get("build_system", "python")
            deps = [
                ln.split("==")[0].split(">=")[0].strip()
                for ln in requirements.read_text(encoding="utf-8", errors="replace").splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
            facts["python_dependencies"] = deps[:30]

        pkg_json = root / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
                facts["build_system"] = facts.get("build_system", "node")
                facts["node_dependencies"] = list(pkg.get("dependencies", {}).keys())[:30]
                deps = pkg.get("dependencies", {})
                if isinstance(deps, dict):
                    if "react" in deps:
                        facts.setdefault("frameworks", []).append("React")
                    if "vue" in deps:
                        facts.setdefault("frameworks", []).append("Vue")
                    if "next" in deps:
                        facts.setdefault("frameworks", []).append("Next.js")
            except (json.JSONDecodeError, OSError):
                pass

        go_mod = root / "go.mod"
        if go_mod.exists():
            facts["build_system"] = facts.get("build_system", "go")

        cargo = root / "Cargo.toml"
        if cargo.exists():
            facts["build_system"] = facts.get("build_system", "rust")

        top_dirs = sorted(
            [
                d.name
                for d in root.iterdir()
                if d.is_dir()
                and not d.name.startswith(".")
                and d.name
                not in ("node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build")
            ]
        )[:20]
        facts["directory_structure"] = top_dirs

        py_count = len(list(root.rglob("*.py")))
        js_count = len(list(root.rglob("*.js"))) + len(list(root.rglob("*.ts")))
        tsx_count = len(list(root.rglob("*.tsx")))
        facts["file_counts"] = {
            "python": py_count,
            "javascript_typescript": js_count + tsx_count,
        }

        with self._lock:
            self._facts = facts
            self._save_unlocked()
        return facts

    def format_for_prompt(self) -> str:
        with self._lock:
            facts = dict(self._facts)
        if not facts:
            return ""
        parts: list[str] = []
        if facts.get("build_system"):
            parts.append(f"Build: {facts['build_system']}")
        fw = facts.get("frameworks")
        if fw:
            uniq = []
            for x in fw:
                if x not in uniq:
                    uniq.append(x)
            parts.append(f"Frameworks: {', '.join(uniq)}")
        dirs = facts.get("directory_structure")
        if dirs:
            parts.append(f"Top-level dirs: {', '.join(dirs[:12])}")
        fc = facts.get("file_counts")
        if fc:
            parts.append(
                f"Approx file counts: py={fc.get('python', 0)}, js/ts/tsx={fc.get('javascript_typescript', 0)}"
            )
        return "\n".join(parts)


class ProjectMemory:
    """Per-project memory: Markdown + auto facts."""

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir).resolve()
        mem_dir = self.project_dir / ".butler" / "memory"
        mem_dir.mkdir(parents=True, exist_ok=True)
        self.markdown = MarkdownMemory(mem_dir / "MEMORY.md")
        self.facts = ProjectFactsStore(mem_dir / "facts.json")

    @classmethod
    def for_project(cls, project: Path | str) -> ProjectMemory:
        return cls(Path(project))

    def get_context_for_agent(self, role: str) -> str:
        key = (role or "default").strip().lower()
        sections = _ROLE_SECTIONS.get(key)
        if sections is None:
            for prefix, secs in _ROLE_SECTIONS.items():
                if key.startswith(prefix):
                    sections = secs
                    break
        if sections is None:
            sections = _ROLE_SECTIONS["default"]

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
        return p.read_text(encoding="utf-8")
