"""Project-level memory: markdown knowledge and auto-extracted facts."""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
import logging

from butler.io.safe_load import safe_load_json

logger = logging.getLogger(__name__)

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

_SENSITIVE_PII_RE = re.compile(
    r"("
    r"1[3-9]\d{9}"
    r"|sk-[a-z0-9]{8,}"
    r"|eyJ[a-z0-9_-]{10,}\.[a-z0-9_-]+\.[a-z0-9_-]+"
    r"|[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"
    r"|\b(?:api[_-]?key|secret|password|token|credential)s?\b"
    r"|密码|密钥|口令|身份证|银行卡|手机号"
    r")",
    re.I,
)

_SENSITIVE_PENDING_KEYWORDS = frozenset(
    {
        "批准",
        "permission",
        "owner only",
        "始终允许",
        "wechat_id",
        "chat_id",
        "credential",
        "credentials",
    }
)


def memory_auto_fact_enabled() -> bool:
    """When false, ``classification=auto`` always queues for Owner review."""
    from butler.env_parse import env_truthy

    return env_truthy("BUTLER_MEMORY_AUTO_FACT", default=True)


def _looks_sensitive_memory(content: str) -> bool:
    text = (content or "").strip()
    if not text:
        return False
    if _SENSITIVE_PII_RE.search(text):
        return True
    lower = text.lower()
    return any(kw in lower for kw in _SENSITIVE_PENDING_KEYWORDS)


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
    "dev_agent": ("Architecture", "Patterns", "API", "Notes"),
    "impl": ("Architecture", "Patterns", "API"),
    "code": ("Architecture", "Patterns", "API"),
    "content": ("Notes", "Patterns", "Decisions"),
    "content_agent": ("Notes", "Patterns", "Decisions"),
    "review": ("Architecture", "Decisions", "Patterns"),
    "reviewer": ("Architecture", "Decisions", "Patterns"),
    "review_agent": ("Architecture", "Decisions", "Patterns"),
    "lead": ("Architecture", "Decisions", "Notes"),
    "butler": ("Decisions", "Notes", "Architecture"),
    "plan": ("Architecture", "Decisions", "Notes"),
    "architect": ("Architecture", "Decisions", "Patterns", "API"),
    "default": ("Architecture", "Decisions", "Patterns", "API", "Notes"),
}

_ROLE_PREFETCH_PROJECT_MAX_CHARS: dict[str, int] = {
    "lead": 800,
    "butler": 900,
    "content": 900,
    "content_agent": 900,
    "review": 1000,
    "review_agent": 1000,
    "dev": 1200,
    "dev_agent": 1200,
}


def sections_for_agent_role(role: str) -> tuple[str, ...]:
    """MEMORY.md sections to inject for a role (prefetch fallback + filtering)."""
    key = (role or "default").strip().lower()
    sections = _ROLE_SECTIONS.get(key)
    if sections is not None:
        return sections
    for prefix, secs in _ROLE_SECTIONS.items():
        if prefix != "default" and key.startswith(prefix):
            return secs
    return _ROLE_SECTIONS["default"]


def project_prefetch_max_chars(role: str, *, default: int) -> int:
    """Per-role cap on project MEMORY fallback block size."""
    key = (role or "default").strip().lower()
    if key in _ROLE_PREFETCH_PROJECT_MAX_CHARS:
        return _ROLE_PREFETCH_PROJECT_MAX_CHARS[key]
    for prefix, cap in _ROLE_PREFETCH_PROJECT_MAX_CHARS.items():
        if key.startswith(prefix):
            return cap
    return default


def filter_memory_hits_by_role(
    hits: list[dict[str, Any]],
    role: str,
) -> list[dict[str, Any]]:
    """Keep only query-aligned bullets whose section matches the active role."""
    allowed = set(sections_for_agent_role(role))
    out: list[dict[str, Any]] = []
    for hit in hits:
        sec = (hit.get("section") or "Notes").strip() or "Notes"
        if sec in allowed:
            out.append(hit)
    return out

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
        if _looks_sensitive_memory(content):
            return "pending"
        if any(u in lower for u in _PENDING_UNCERTAIN):
            return "pending"
        for kw in _DECISION_KEYWORDS:
            if kw in lower:
                return "pending"
        if not memory_auto_fact_enabled():
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

    def reject_pending(self, idx: int) -> bool:
        """Remove one Pending entry without promoting to a formal section."""
        pending = self.list_pending()
        if not (0 <= idx < len(pending)):
            return False
        item = pending[idx]
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
        return True

    def reject_all_pending(self) -> int:
        count = 0
        while self.list_pending():
            if not self.reject_pending(0):
                break
            count += 1
        return count

    _FORMAL_BULLET_RE = re.compile(r"^-\s*\[[^\]]+\]\s*(.+)$")

    def list_formal_bullets(self) -> list[dict[str, str]]:
        """All non-Pending bullets: section + content body."""
        out: list[dict[str, str]] = []
        for section, body in self.get_all_sections().items():
            if section == "Pending":
                continue
            for line in (body or "").splitlines():
                m = self._FORMAL_BULLET_RE.match(line.strip())
                if not m:
                    continue
                content = m.group(1).strip()
                if content:
                    out.append({"section": section, "content": content, "line": line.strip()})
        return out

    def remove_bullet(self, section: str, content: str) -> bool:
        """Remove a formal bullet whose body exactly matches ``content``."""
        section = normalize_section_name(section)
        target = (content or "").strip()
        if not target:
            return False
        with self._lock:
            text = self._read_unlocked()
            block = self._extract_section(text, section)
            if not block:
                return False
            new_lines: list[str] = []
            removed = False
            for ln in block.splitlines():
                m = self._FORMAL_BULLET_RE.match(ln.strip())
                if not removed and m and m.group(1).strip() == target:
                    removed = True
                    continue
                if ln.strip():
                    new_lines.append(ln)
            if not removed:
                return False
            self._replace_section_body_unlocked(text, section, "\n".join(new_lines).strip())
        return True

    def replace_bullet(self, section: str, old_content: str, new_content: str) -> bool:
        """Replace bullet body; returns False if old line not found."""
        old = (old_content or "").strip()
        new = (new_content or "").strip()
        if not old or not new:
            return False
        if not self.remove_bullet(section, old):
            return False
        self.append(section, new, classification="fact")
        return True

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
            # Audit R2-19: corrupt project facts file used to silently
            # drop every fact on the next read. safe_load renames
            # the corrupt file for forensic retention, logs WARNING
            # with exc_info, and records the event for /诊断.
            self._facts = safe_load_json(
                self.path, default={}, kind="memory_project_facts",
            )
            if not isinstance(self._facts, dict):
                self._facts = {}

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._facts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            from butler.memory.knowledge_db import sync_facts_json_to_knowledge_db

            sync_facts_json_to_knowledge_db(self.path)
        except Exception as exc:
            logger.debug("save unlocked skipped: %s", exc)
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

    def refresh(self, project_dir: Path | None = None) -> dict[str, Any]:
        """Scan project tree and persist facts.json (idempotent)."""
        root = Path(project_dir or self.path.parent.parent.parent).resolve()
        return self.auto_extract(root)

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

    def refresh_facts(self) -> dict[str, Any]:
        """Re-scan workspace and update facts.json."""
        return self.facts.refresh(self.project_dir)

    def facts_for_prefetch(self, *, max_chars: int = 400) -> str:
        """Compact auto-extracted facts for per-turn memory injection."""
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
        return text
