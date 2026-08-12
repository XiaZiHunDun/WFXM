from __future__ import annotations

import logging
import re
import threading
from datetime import datetime
from pathlib import Path

from .classifiers import _looks_sensitive_memory, looks_correction_memory, memory_auto_approve_mode, memory_auto_fact_enabled
from .constants import _DECISION_KEYWORDS, _PENDING_LINE_RE, _SECTION_ALIASES, _SECTION_ORDER, _PENDING_UNCERTAIN

logger = logging.getLogger(__name__)


def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def normalize_section_name(section: str) -> str:
    raw = (section or "Notes").strip()
    if raw in _SECTION_ORDER:
        return raw
    return _SECTION_ALIASES.get(raw, raw)


class MarkdownMemory:
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
        mode = memory_auto_approve_mode()
        if mode == "correction":
            return "fact" if looks_correction_memory(content) else "pending"
        if mode == "all":
            return "fact" if memory_auto_fact_enabled() else "pending"
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
        payload = content.strip()
        if not payload:
            return
        text = self._read_unlocked()
        marker = f"## {section}"
        if self._bullet_exists_unlocked(text, section, payload):
            logger.debug(
                "Skip duplicate bullet in section %r: %s",
                section,
                payload[:80],
            )
            return
        ts = _now_ts()
        entry = f"- [{ts}] {payload}\n"
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

    def _bullet_exists_unlocked(self, text: str, section: str, payload: str) -> bool:
        block = self._extract_section(text, section)
        if not block:
            return False
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped.startswith("- "):
                continue
            match = self._FORMAL_BULLET_RE.match(stripped)
            body = match.group(1).strip() if match else stripped[2:].strip()
            if body == payload:
                return True
        return False

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
