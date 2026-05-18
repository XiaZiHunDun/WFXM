"""Dual-scope memory system: global (owner prefs) + project-level (knowledge base).

Key design:
- Global memory: ~/.butler/memory/ — owner preferences, cross-project experience
- Project memory: projects/X/.butler/memory/ — architecture, decisions, patterns, issues
- Session memory is separate (in SessionStore) and ephemeral

Hybrid persistence: MEMORY.md stays the human-readable source for read()/append(),
plus optional SQLite + FTS5 (lazy) for BM25-ranked retrieval and triplet facts.
"""

from __future__ import annotations

import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.core.project_manager import Project


_PROJECT_MEMORY_SECTIONS = (
    "## 架构与设计\n\n",
    "## 关键决策\n\n",
    "## 代码模式与约定\n\n",
    "## 已知问题\n\n",
    "## 当前状态\n\n",
)

_TRIPLET_PIPE_RE = re.compile(
    r"^\s*(?P<s>[^|]+?)\s*\|\s*(?P<r>[^|]+?)\s*\|\s*(?P<o>.+?)\s*$"
)
_TRIPLET_ARROW_RE = re.compile(
    r"^\s*(?P<s>.+?)\s*(?:→|->)\s*(?P<r>.+?)\s*(?:→|->)\s*(?P<o>.+?)\s*$"
)
_BULLET_RE = re.compile(r"^- \[(?P<ts>[^\]]+)\]\s*(?P<content>.*)\s*$")

_DECISION_KEYWORDS = frozenset({
    "决定", "决策", "选择", "改为", "替换", "弃用", "废弃", "迁移",
    "重构", "重写", "升级", "降级", "切换", "采用", "放弃", "转向",
    "decided", "decision", "chose", "switch", "migrate", "replace",
    "deprecate", "adopt", "abandon",
})


def classify_memory(content: str) -> str:
    """Classify memory as 'fact' (auto-approved) or 'decision' (needs approval).

    Facts: objective technical details (framework versions, file paths, config values).
    Decisions: subjective choices that could be wrong if LLM hallucinated.
    """
    content_lower = content.lower()
    for kw in _DECISION_KEYWORDS:
        if kw in content_lower:
            return "decision"
    return "fact"


def _fts5_phrase(query: str) -> str:
    """Wrap query as an FTS5 phrase (handles quotes)."""
    return '"' + query.replace('"', '""') + '"'


class SemanticMemoryIndex:
    """SQLite + FTS5 (BM25) index for memory entries and triplet facts."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        conn = self._connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY,
                section TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                access_count INTEGER NOT NULL DEFAULT 0,
                decay_score REAL NOT NULL DEFAULT 1.0
            );

            CREATE TABLE IF NOT EXISTS triplets (
                id INTEGER PRIMARY KEY,
                subject TEXT NOT NULL,
                relation TEXT NOT NULL,
                object TEXT NOT NULL,
                source_entry_id INTEGER,
                timestamp REAL NOT NULL,
                FOREIGN KEY (source_entry_id) REFERENCES entries(id)
            );

            CREATE INDEX IF NOT EXISTS idx_triplets_subject ON triplets(subject);
            CREATE INDEX IF NOT EXISTS idx_triplets_relation ON triplets(relation);
            CREATE INDEX IF NOT EXISTS idx_triplets_object ON triplets(object);
            CREATE INDEX IF NOT EXISTS idx_triplets_source ON triplets(source_entry_id);

            CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                section,
                content,
                tokenize='porter unicode61',
                content='entries',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
                INSERT INTO entries_fts(rowid, section, content)
                VALUES (new.id, new.section, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
                INSERT INTO entries_fts(entries_fts, rowid, section, content)
                VALUES('delete', old.id, old.section, old.content);
            END;
            CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
                INSERT INTO entries_fts(entries_fts, rowid, section, content)
                VALUES('delete', old.id, old.section, old.content);
                INSERT INTO entries_fts(rowid, section, content)
                VALUES (new.id, new.section, new.content);
            END;
            """
        )
        conn.commit()

    def entry_count(self) -> int:
        conn = self._connect()
        row = conn.execute("SELECT COUNT(*) AS c FROM entries").fetchone()
        return int(row["c"]) if row else 0

    def clear_all(self) -> None:
        conn = self._connect()
        conn.execute("DELETE FROM triplets")
        conn.execute("DELETE FROM entries")
        conn.commit()

    def add_entry(self, section: str, content: str, ts: float | None = None) -> int:
        self._init_schema()
        conn = self._connect()
        if ts is None:
            ts = time.time()
        cur = conn.execute(
            "INSERT INTO entries(section, content, timestamp, access_count, decay_score) "
            "VALUES (?, ?, ?, 0, 1.0)",
            (section, content, ts),
        )
        conn.commit()
        return int(cur.lastrowid)

    def add_triplet(
        self,
        subject: str,
        relation: str,
        object: str,
        source_entry_id: int | None = None,
        ts: float | None = None,
    ) -> int:
        self._init_schema()
        conn = self._connect()
        if ts is None:
            ts = time.time()
        cur = conn.execute(
            "INSERT INTO triplets(subject, relation, object, source_entry_id, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (subject.strip(), relation.strip(), object.strip(), source_entry_id, ts),
        )
        conn.commit()
        return int(cur.lastrowid)

    def query_triplets(
        self,
        subject: str | None = None,
        relation: str | None = None,
        object: str | None = None,
    ) -> list[tuple[Any, ...]]:
        self._init_schema()
        conn = self._connect()
        clauses: list[str] = []
        params: list[Any] = []
        if subject is not None:
            clauses.append("subject = ?")
            params.append(subject)
        if relation is not None:
            clauses.append("relation = ?")
            params.append(relation)
        if object is not None:
            clauses.append("object = ?")
            params.append(object)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT id, subject, relation, object, source_entry_id, timestamp FROM triplets{where}",
            params,
        ).fetchall()
        return [tuple(r) for r in rows]

    def search_ranked(self, query: str, max_items: int) -> list[sqlite3.Row]:
        self._init_schema()
        conn = self._connect()
        if not query.strip():
            rows = conn.execute(
                "SELECT id, section, content, timestamp, access_count, decay_score FROM entries "
                "ORDER BY decay_score DESC, timestamp DESC LIMIT ?",
                (max_items,),
            ).fetchall()
            return list(rows)

        q_plain = query.strip()
        match_q = _fts5_phrase(q_plain)
        try:
            rows = conn.execute(
                """
                SELECT e.id, e.section, e.content, e.timestamp, e.access_count, e.decay_score,
                       bm25(entries_fts) AS rank
                FROM entries_fts
                JOIN entries AS e ON e.id = entries_fts.rowid
                WHERE entries_fts MATCH ?
                ORDER BY (bm25(entries_fts) / MAX(e.decay_score, 0.01)) ASC
                LIMIT ?
                """,
                (match_q, max_items),
            ).fetchall()
            return list(rows)
        except sqlite3.OperationalError:
            rows = conn.execute(
                """
                SELECT id, section, content, timestamp, access_count, decay_score
                FROM entries
                WHERE instr(lower(section), lower(?)) OR instr(lower(content), lower(?))
                ORDER BY decay_score DESC, timestamp DESC
                LIMIT ?
                """,
                (q_plain, q_plain, max_items),
            ).fetchall()
            return list(rows)

    def bump_access(self, entry_ids: list[int]) -> None:
        if not entry_ids:
            return
        self._init_schema()
        conn = self._connect()
        conn.executemany(
            "UPDATE entries SET access_count = access_count + 1 WHERE id = ?",
            [(i,) for i in entry_ids],
        )
        conn.commit()

    def decay_memories(self, half_life_days: float = 30) -> None:
        self._init_schema()
        if half_life_days <= 0:
            return
        conn = self._connect()
        half_life_sec = float(half_life_days) * 86400.0
        # Continuous half-life: multiply current score by 2^(-elapsed/half_life)
        conn.execute(
            """
            UPDATE entries
            SET decay_score = decay_score * POWER(0.5, ( ? - timestamp ) / ? )
            """,
            (time.time(), half_life_sec),
        )
        conn.commit()


def _parse_bullet_timestamp(bullet_ts: str) -> float:
    try:
        dt = datetime.strptime(bullet_ts.strip(), "%Y-%m-%d %H:%M")
        return dt.timestamp()
    except ValueError:
        return time.time()


def _extract_triplets_from_line(line: str) -> list[tuple[str, str, str]]:
    m = _BULLET_RE.match(line)
    text = m.group("content") if m else line.strip().lstrip("- ").strip()
    if not text:
        return []
    pipe = _TRIPLET_PIPE_RE.match(text)
    if pipe:
        return [
            (
                pipe.group("s").strip(),
                pipe.group("r").strip(),
                pipe.group("o").strip(),
            )
        ]
    arrow = _TRIPLET_ARROW_RE.match(text)
    if arrow:
        return [
            (
                arrow.group("s").strip(),
                arrow.group("r").strip(),
                arrow.group("o").strip(),
            )
        ]
    return []


class MemoryStore:
    """Manages persistent memory as structured Markdown + optional FTS index."""

    def __init__(self, memory_dir: Path, scope: str = "global"):
        self.memory_dir = memory_dir
        self.scope = scope
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = memory_dir / "MEMORY.md"
        self._index: SemanticMemoryIndex | None = None
        self._semantic_active = False
        if not self.index_file.exists():
            self._init_memory()

    @property
    def _db_path(self) -> Path:
        return self.memory_dir / "semantic_memory.db"

    def _get_index(self) -> SemanticMemoryIndex:
        if self._index is None:
            bootstrap = SemanticMemoryIndex(self._db_path)
            bootstrap._init_schema()  # noqa: SLF001
            if bootstrap.entry_count() == 0:
                bootstrap.close()
                self._rebuild_index_from_disk()
            else:
                self._index = bootstrap
            self._semantic_active = True
        return self._index

    def _rebuild_index_from_disk(self) -> None:
        ix = SemanticMemoryIndex(self._db_path)
        ix._init_schema()  # noqa: SLF001
        ix.clear_all()

        text = ""
        if self.index_file.exists():
            text = self.index_file.read_text(encoding="utf-8")
        section = "__preamble__"
        now = time.time()
        for raw_line in text.splitlines():
            line = raw_line.rstrip("\n")
            if line.startswith("## ") and line[3:].strip():
                section = line[3:].strip()
                continue
            m = _BULLET_RE.match(line)
            if m:
                ts = _parse_bullet_timestamp(m.group("ts"))
                content = m.group("content").strip()
                entry_id = ix.add_entry(section, content, ts=ts)
                for subj, rel, obj in _extract_triplets_from_line(line):
                    ix.add_triplet(subj, rel, obj, source_entry_id=entry_id, ts=ts)
            elif line.strip() and not line.strip().startswith("#"):
                ix.add_entry(section, line.strip(), ts=now)

        for md in sorted(self.memory_dir.glob("*.md")):
            if md.name == "MEMORY.md":
                continue
            topic = md.stem
            body = md.read_text(encoding="utf-8").strip()
            if body:
                entry_id = ix.add_entry(f"topic:{topic}", body, ts=md.stat().st_mtime)
                for ln in body.splitlines():
                    for subj, rel, obj in _extract_triplets_from_line(ln):
                        ix.add_triplet(subj, rel, obj, source_entry_id=entry_id)

        self._index = ix
        self._semantic_active = True

    def _ensure_entry_indexed(self, section: str, bullet_line: str) -> None:
        if not self._semantic_active:
            return
        m = _BULLET_RE.match(bullet_line.rstrip("\n"))
        if not m:
            return
        ts = _parse_bullet_timestamp(m.group("ts"))
        content = m.group("content").strip()
        ix = self._get_index()
        entry_id = ix.add_entry(section, content, ts=ts)
        for subj, rel, obj in _extract_triplets_from_line(bullet_line):
            ix.add_triplet(subj, rel, obj, source_entry_id=entry_id, ts=ts)

    def _index_topic_body(self, topic: str, body: str) -> None:
        if not self._semantic_active:
            return
        ix = self._get_index()
        ts = time.time()
        entry_id = ix.add_entry(f"topic:{topic}", body.strip(), ts=ts)
        for ln in body.splitlines():
            for subj, rel, obj in _extract_triplets_from_line(ln):
                ix.add_triplet(subj, rel, obj, source_entry_id=entry_id, ts=ts)

    @classmethod
    def global_store(cls) -> MemoryStore:
        from butler.config.settings import settings

        return cls(settings.butler_home / "memory", scope="global")

    @classmethod
    def for_project(cls, project: Project) -> MemoryStore:
        memory_dir = project.workspace / ".butler" / "memory"
        return cls(memory_dir, scope="project")

    @classmethod
    def for_project_name(cls, project_name: str) -> MemoryStore | None:
        from butler.core.project_manager import project_manager

        proj = project_manager.get_project(project_name)
        if proj:
            return cls.for_project(proj)
        return None

    def _init_memory(self) -> None:
        if self.scope == "global":
            self.index_file.write_text(
                "# 管家记忆\n\n"
                f"> 创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                "## 主公偏好\n\n"
                "## 经验教训\n\n"
                "## 跨项目备忘\n\n",
                encoding="utf-8",
            )
        else:
            self.index_file.write_text(
                "# 项目记忆\n\n"
                f"> 创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                + "".join(_PROJECT_MEMORY_SECTIONS),
                encoding="utf-8",
            )

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

        bullet = entry.rstrip("\n")
        self._ensure_entry_indexed(section, bullet)

    def get_context(self, max_lines: int = 50) -> str:
        text = self.read()
        lines = text.splitlines()
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines.append("... (更多记忆已截断)")
        return "\n".join(lines)

    def get_relevant_context(self, query: str, max_items: int = 10) -> str:
        ix = self._get_index()
        rows = ix.search_ranked(query, max(max_items, 1))
        if not rows:
            return ""
        ids = [int(r["id"]) for r in rows]
        ix.bump_access(ids)
        parts: list[str] = []
        for r in rows:
            sec = r["section"]
            body = r["content"]
            parts.append(f"## {sec}\n- {body}\n")
        return "\n".join(parts).strip()

    def save_topic(self, topic: str, content: str) -> None:
        topic_file = self.memory_dir / f"{topic}.md"
        topic_file.write_text(content, encoding="utf-8")
        self._index_topic_body(topic, content)

    def read_topic(self, topic: str) -> str:
        topic_file = self.memory_dir / f"{topic}.md"
        if topic_file.exists():
            return topic_file.read_text(encoding="utf-8")
        return ""

    def bulk_update(self, updates: dict[str, str]) -> None:
        """Update multiple sections at once (used by memory extractor)."""
        for sect, raw in updates.items():
            if raw.strip():
                self.append(sect, raw)

    @property
    def pending_file(self) -> Path:
        return self.memory_dir / "PENDING_DECISIONS.md"

    def append_with_classification(self, section: str, content: str) -> str:
        """Append memory with auto-classification. Returns 'fact' or 'decision'."""
        kind = classify_memory(content)
        if kind == "decision":
            self._append_pending(section, content)
        else:
            self.append(section, content)
        return kind

    def _append_pending(self, section: str, content: str) -> None:
        """Write a decision memory to pending approval file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"- [{timestamp}] [{section}] {content}\n"
        existing = ""
        if self.pending_file.exists():
            existing = self.pending_file.read_text(encoding="utf-8")
        if not existing:
            existing = "# 待审核的决策记忆\n\n> 这些记忆由 AI 自动提炼，需要用户确认后才会正式写入记忆库\n\n"
        existing += entry
        self.pending_file.write_text(existing, encoding="utf-8")

    def get_pending_decisions(self) -> list[dict]:
        """Get all pending decision memories."""
        if not self.pending_file.exists():
            return []
        text = self.pending_file.read_text(encoding="utf-8")
        results = []
        for line in text.splitlines():
            m = re.match(r'^- \[([^\]]+)\] \[([^\]]+)\] (.+)$', line)
            if m:
                results.append({
                    "timestamp": m.group(1),
                    "section": m.group(2),
                    "content": m.group(3),
                })
        return results

    def approve_pending(self, indices: list[int] | None = None) -> int:
        """Approve pending decisions (all if indices is None). Returns count approved."""
        pending = self.get_pending_decisions()
        if not pending:
            return 0

        if indices is None:
            to_approve = pending
        else:
            to_approve = [pending[i] for i in indices if 0 <= i < len(pending)]

        for item in to_approve:
            self.append(item["section"], item["content"])

        if indices is None:
            self.pending_file.unlink(missing_ok=True)
        else:
            approved_set = {(item["timestamp"], item["content"]) for item in to_approve}
            remaining_lines = ["# 待审核的决策记忆\n", "\n", "> 这些记忆由 AI 自动提炼，需要用户确认后才会正式写入记忆库\n", "\n"]
            for item in pending:
                if (item["timestamp"], item["content"]) not in approved_set:
                    remaining_lines.append(f"- [{item['timestamp']}] [{item['section']}] {item['content']}\n")
            self.pending_file.write_text("".join(remaining_lines), encoding="utf-8")

        return len(to_approve)

    def reject_pending(self, indices: list[int]) -> int:
        """Reject (remove) pending decisions. Returns count rejected."""
        pending = self.get_pending_decisions()
        if not pending:
            return 0
        to_reject = {i for i in indices if 0 <= i < len(pending)}
        remaining_lines = ["# 待审核的决策记忆\n", "\n", "> 这些记忆由 AI 自动提炼，需要用户确认后才会正式写入记忆库\n", "\n"]
        for i, item in enumerate(pending):
            if i not in to_reject:
                remaining_lines.append(f"- [{item['timestamp']}] [{item['section']}] {item['content']}\n")
        self.pending_file.write_text("".join(remaining_lines), encoding="utf-8")
        return len(to_reject)

    def add_triplet(self, subject: str, relation: str, object: str, source_id: int | None = None) -> None:
        self._get_index().add_triplet(subject, relation, object, source_entry_id=source_id)

    def query_triplets(
        self,
        subject: str | None = None,
        relation: str | None = None,
        object: str | None = None,
    ) -> list[tuple]:
        return self._get_index().query_triplets(subject=subject, relation=relation, object=object)

    def decay_memories(self, half_life_days: float = 30) -> None:
        self._get_index().decay_memories(half_life_days=half_life_days)
