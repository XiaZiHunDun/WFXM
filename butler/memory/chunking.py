"""Markdown hierarchical chunking for project docs (RAGFlow title_chunker subset)."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from butler.env_parse import env_truthy, float_env

logger = logging.getLogger(__name__)

_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_HEADING_META_RE = re.compile(r"^\[headings:\s*(.+?)\]\s*$", re.MULTILINE)
_DOC_META_RE = re.compile(r"^\[doc:\s*(.+?)\]\s*$", re.MULTILINE)
_PARENT_META_RE = re.compile(r"^\[parent:\s*(.+?)\]\s*$", re.MULTILINE)

DEFAULT_INDEX_REL_PATHS = (
    ".butler/memory/MEMORY.md",
    "DESIGN.md",
    "AGENTS.md",
    "docs/architecture/v4-architecture.md",
    "STRUCTURE.md",
)


@dataclass(frozen=True)
class MarkdownChunk:
    content: str
    heading_path: tuple[str, ...]
    heading_level: int
    chunk_index: int
    source_path: str
    parent_doc_id: str
    source_id: str


def markdown_chunking_enabled() -> bool:
    return bool(env_truthy("BUTLER_MARKDOWN_CHUNKING", default=True))


def chunk_min_chars() -> int:
    try:
        from butler.env_parse import int_env

        return int(int_env("BUTLER_MARKDOWN_CHUNK_MIN_CHARS", 256, min=64))
    except ValueError:
        return 256


def chunk_max_chars() -> int:
    try:
        from butler.env_parse import int_env

        return int(int_env("BUTLER_MARKDOWN_CHUNK_MAX_CHARS", 4000, min=512))
    except ValueError:
        return 4000


def heading_boost_per_token() -> float:
    try:
        return float(max(0.0, float_env("BUTLER_MARKDOWN_HEADING_BOOST", 0.18)))
    except ValueError:
        return 0.18


def index_glob_paths() -> tuple[str, ...]:
    raw = os.getenv("BUTLER_MARKDOWN_INDEX_PATHS", "").strip()
    if not raw:
        return DEFAULT_INDEX_REL_PATHS
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return tuple(str(x).strip() for x in parsed if str(x).strip())
        except json.JSONDecodeError:
            pass
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def _slug_part(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return slug[:48] or "section"


def heading_path_slug(path: tuple[str, ...]) -> str:
    return "-".join(_slug_part(p) for p in path if p)[:96] or "root"


def parent_doc_id(project_name: str, rel_path: str) -> str:
    rel = rel_path.replace("\\", "/").lstrip("/")
    return f"{project_name}:md:{rel}"


def chunk_source_id(
    project_name: str,
    rel_path: str,
    heading_path: tuple[str, ...],
    chunk_index: int,
) -> str:
    rel = rel_path.replace("\\", "/").lstrip("/")
    hslug = heading_path_slug(heading_path) if heading_path else "root"
    return f"{project_name}:md:{rel}#h{hslug}:{chunk_index:04d}"


def format_chunk_embedding_text(
    chunk: MarkdownChunk,
) -> str:
    path_label = " > ".join(chunk.heading_path) if chunk.heading_path else "(root)"
    lines = [
        f"[doc: {chunk.source_path}]",
        f"[headings: {path_label}]",
        f"[parent: {chunk.parent_doc_id}]",
        "",
        chunk.content.strip(),
    ]
    return "\n".join(lines).strip()


def _split_oversized_body(body: str, *, max_chars: int) -> list[str]:
    text = (body or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    buf: list[str] = []
    size = 0
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if size + len(para) + 2 > max_chars and buf:
            parts.append("\n\n".join(buf))
            buf = [para]
            size = len(para)
        else:
            buf.append(para)
            size += len(para) + 2
    if buf:
        parts.append("\n\n".join(buf))
    if not parts:
        return [text[:max_chars]]
    return parts


def chunk_markdown_hierarchical(
    markdown: str,
    *,
    rel_path: str,
    project_name: str,
    min_chars: int | None = None,
    max_chars: int | None = None,
) -> list[MarkdownChunk]:
    """Split markdown by heading tree; merge tiny sections; split large bodies."""
    min_c = min_chars if min_chars is not None else chunk_min_chars()
    max_c = max_chars if max_chars is not None else chunk_max_chars()
    rel = rel_path.replace("\\", "/").lstrip("/")
    parent_id = parent_doc_id(project_name, rel)

    sections: list[tuple[tuple[str, ...], int, str]] = []
    stack: list[tuple[int, str]] = []
    body_lines: list[str] = []

    def flush_section() -> None:
        body = "\n".join(body_lines).strip()
        body_lines.clear()
        path = tuple(title for _, title in stack)
        level = stack[-1][0] if stack else 0
        if body or not sections:
            sections.append((path, level, body))

    for line in (markdown or "").splitlines():
        m = _HEADING_LINE_RE.match(line)
        if m:
            flush_section()
            level = len(m.group(1))
            title = m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            continue
        body_lines.append(line)
    flush_section()

    if not sections and (markdown or "").strip():
        sections = [((), 0, markdown.strip())]

    merged: list[tuple[tuple[str, ...], int, str]] = []
    for path, level, body in sections:
        if merged and len(body) < min_c and len(merged[-1][2]) < max_c:
            prev_path, prev_level, prev_body = merged[-1]
            merged[-1] = (prev_path, prev_level, f"{prev_body}\n\n{body}".strip())
        else:
            merged.append((path, level, body))

    out: list[MarkdownChunk] = []
    idx = 0
    for path, level, body in merged:
        if not body.strip():
            continue
        for part in _split_oversized_body(body, max_chars=max_c):
            if len(part) < min_c and out:
                prev = out[-1]
                merged_text = f"{prev.content}\n\n{part}".strip()
                out[-1] = MarkdownChunk(
                    content=merged_text,
                    heading_path=prev.heading_path,
                    heading_level=prev.heading_level,
                    chunk_index=prev.chunk_index,
                    source_path=rel,
                    parent_doc_id=parent_id,
                    source_id=prev.source_id,
                )
                continue
            cid = chunk_source_id(project_name, rel, path, idx)
            out.append(
                MarkdownChunk(
                    content=part,
                    heading_path=path,
                    heading_level=level,
                    chunk_index=idx,
                    source_path=rel,
                    parent_doc_id=parent_id,
                    source_id=cid,
                )
            )
            idx += 1
    return out


def discover_markdown_files(project_dir: Path, workspace: Path) -> list[Path]:
    """Resolve configured relative paths under project / workspace."""
    found: list[Path] = []
    seen: set[str] = set()
    for root in (project_dir.resolve(), workspace.resolve()):
        if not root.is_dir():
            continue
        for pattern in index_glob_paths():
            pat = pattern.strip().replace("\\", "/").lstrip("/")
            if not pat:
                continue
            try:
                hits = sorted(root.glob(pat))
            except OSError:
                continue
            for hit in hits:
                if not hit.is_file() or hit.suffix.lower() != ".md":
                    continue
                key = str(hit.resolve())
                if key in seen:
                    continue
                seen.add(key)
                found.append(hit.resolve())
    ingest_root = workspace.resolve() / ".butler" / "ingest"
    if ingest_root.is_dir():
        for hit in sorted(ingest_root.rglob("*.md")):
            if not hit.is_file():
                continue
            key = str(hit.resolve())
            if key in seen:
                continue
            seen.add(key)
            found.append(hit.resolve())
    try:
        from butler.memory.document_ingest import pilot_dirs_from_stack

        for pilot_root in pilot_dirs_from_stack(workspace):
            if not pilot_root.is_dir():
                continue
            for hit in sorted(pilot_root.rglob("*.md")):
                if not hit.is_file():
                    continue
                key = str(hit.resolve())
                if key in seen:
                    continue
                seen.add(key)
                found.append(hit.resolve())
    except ImportError:
        logger.debug("document_ingest unavailable; skip ingest_pilot_dirs markdown")
    return found


def rel_path_for_index(file_path: Path, project_dir: Path, workspace: Path) -> str:
    path = file_path.resolve()
    for base in (workspace.resolve(), project_dir.resolve()):
        try:
            return path.relative_to(base).as_posix()
        except ValueError:
            continue
    return path.name


def parse_chunk_metadata(content: str) -> dict[str, str]:
    text = str(content or "")
    out: dict[str, str] = {}
    m_doc = _DOC_META_RE.search(text)
    if m_doc:
        out["source_path"] = m_doc.group(1).strip()
    m_head = _HEADING_META_RE.search(text)
    if m_head:
        out["heading_path"] = m_head.group(1).strip()
    m_par = _PARENT_META_RE.search(text)
    if m_par:
        out["parent_source_id"] = m_par.group(1).strip()
    return out


def heading_boost_factor(content: str, query: str) -> float:
    meta = parse_chunk_metadata(content)
    heading = meta.get("heading_path", "")
    if not heading:
        return 1.0
    htok = set(re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]{2,}", heading.lower()))
    qtok = set(re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]{2,}", (query or "").lower()))
    if not htok or not qtok:
        return 1.0
    overlap = len(htok & qtok)
    if overlap <= 0:
        return 1.0
    return 1.0 + heading_boost_per_token() * overlap


def index_markdown_file(
    semantic: Any,
    *,
    project_name: str,
    file_path: Path,
    project_dir: Path,
    workspace: Path,
) -> int:
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("Skip markdown index %s: %s", file_path, exc)
        return 0
    if not text.strip():
        return 0
    rel = rel_path_for_index(file_path, project_dir, workspace)
    chunks = chunk_markdown_hierarchical(
        text,
        rel_path=rel,
        project_name=project_name,
    )
    count = 0
    from butler.memory.chunking_ops import index_markdown_chunk_safe

    for ch in chunks:
        payload = format_chunk_embedding_text(ch)
        if index_markdown_chunk_safe(
            semantic,
            ch,
            project_name=project_name,
            payload=payload,
        ):
            count += 1
    return count


def index_project_markdown_corpus(
    semantic: Any,
    project_dir: Path,
    *,
    project_name: str,
    workspace: Path | None = None,
) -> int:
    ws = (workspace or project_dir).resolve()
    total = 0
    for md_file in discover_markdown_files(project_dir, ws):
        total += index_markdown_file(
            semantic,
            project_name=project_name,
            file_path=md_file,
            project_dir=project_dir,
            workspace=ws,
        )
    return total


__all__ = [
    "MarkdownChunk",
    "chunk_markdown_hierarchical",
    "discover_markdown_files",
    "format_chunk_embedding_text",
    "heading_boost_factor",
    "index_project_markdown_corpus",
    "markdown_chunking_enabled",
    "parse_chunk_metadata",
    "parent_doc_id",
]
