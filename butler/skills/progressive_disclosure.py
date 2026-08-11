"""Progressive skill disclosure — two-tier loading for skill content.

Tier 1 (listing): scan skill roots and expose lightweight :class:`SkillMetadata`
only (names, descriptions, categories).  Token-efficient for LLM tool-picker
decisions where the full skill body is not yet needed.

Tier 2 (loading): on demand, read the full SKILL.md, parse frontmatter, discover
supporting ``references/`` and ``templates/`` siblings, and return a
:class:`SkillContent` bundle.

Design notes
------------
* Stdlib only (``dataclasses``, ``pathlib``, ``re``, ``time``).  No PyYAML
  dependency — we hand-roll a minimal YAML-subset parser sufficient for the
  frontmatter shape used by Butler skills.
* Discovery is I/O conservative: files are prefiltered via ``rglob`` on the
  filename first, then the first ~1 KB is read to confirm frontmatter presence
  before attempting a full parse.
* Platform-aware: skills declaring a ``platform`` frontmatter field that does
  not match the current ``sys.platform`` are silently skipped during discovery.
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

__all__ = [
    "SkillMetadata",
    "SkillContent",
    "parse_skill_frontmatter",
    "SkillRegistry",
    "EXCLUDED_DIR_NAMES",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".github",
        ".hg",
        ".svn",
        ".idea",
        ".vscode",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    }
)

_SKILL_MD_NAMES: tuple[str, ...] = ("SKILL.md", "skill.md")
_SUPPORTED_REF_SUFFIXES: tuple[str, ...] = (
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
    ".jinja",
    ".j2",
    ".tmpl",
    ".template",
)

# Regex used to split YAML frontmatter (between the first two ``---`` lines)
# from the markdown body.  The flag ``re.DOTALL`` makes ``.`` match newlines so
# we can slurp the whole frontmatter block with a single ``.*?``.
_FRONTMATTER_RE = re.compile(
    r"\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)(.*)\Z",
    re.DOTALL,
)

# How many bytes to peek when prefiltering a candidate file.  Enough to cover
# a realistic frontmatter block while keeping the I/O cheap.
_PEEK_BYTES: int = 2048

# Current platform token used for frontmatter ``platform`` matching.  We
# normalise to a handful of common values; anything else falls back to the
# raw ``sys.platform`` string.
_PLATFORM_TOKEN: str = (
    "windows"
    if sys.platform.startswith("win")
    else "macos"
    if sys.platform == "darwin"
    else "linux"
    if sys.platform.startswith("linux")
    else sys.platform
)


# ---------------------------------------------------------------------------
# Frontmatter parsing (minimal YAML subset)
# ---------------------------------------------------------------------------

def _fold_block_text(text: str) -> str:
    """YAML ``>`` block folding: joins lines with a single space.

    Lines that are already blank (``""``) become paragraph breaks (double
    newline); non-empty lines are joined with a single space.
    """

    paragraphs: list[list[str]] = []
    current: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            if current:
                paragraphs.append(current)
                current = []
        else:
            current.append(line.rstrip())
    if current:
        paragraphs.append(current)
    parts: list[str] = []
    for para in paragraphs:
        parts.append(" ".join(para))
    return "\n\n".join(parts)


def _coerce_scalar(raw: str) -> object:
    """Convert a raw YAML scalar into its Python representation.

    Supports: ``null``/``~``, ``true``/``false``, integers, floats, single- or
    double-quoted strings (with basic escape handling), and bare strings.
    """

    s = raw.strip()
    if not s:
        return ""
    low = s.lower()
    if low in {"null", "~", "none"}:
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if (s.startswith('"') and s.endswith('"')) or (
        s.startswith("'") and s.endswith("'")
    ):
        inner = s[1:-1]
        if s.startswith('"'):
            inner = (
                inner.replace('\\"', '"')
                .replace("\\\\", "\\")
                .replace("\\n", "\n")
                .replace("\\t", "\t")
            )
        return inner
    # integer
    try:
        if re.fullmatch(r"[+-]?\d+", s):
            return int(s)
    except ValueError:
        pass
    # float
    try:
        if re.fullmatch(r"[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?", s):
            return float(s)
    except ValueError:
        pass
    return s


class _YAMLError(Exception):
    """Raised (and caught) when frontmatter cannot be parsed."""


def _parse_yaml_mapping(text: str, indent: int) -> dict[str, object]:
    """Parse a YAML mapping block starting at column *indent*."""

    result: dict[str, object] = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        leading = len(line) - len(line.lstrip(" "))
        if leading < indent:
            break
        if leading > indent:
            i += 1
            continue
        content = line[leading:]
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", content)
        if not m:
            i += 1
            continue
        key = m.group(1)
        rest = m.group(2)
        if rest:
            if rest.startswith("[") and rest.endswith("]"):
                inner = rest[1:-1]
                items = [
                    _coerce_scalar(part.strip())
                    for part in inner.split(",")
                    if part.strip()
                ]
                result[key] = items
                i += 1
                continue
            # Inline block scalar indicator, e.g. ``description: |``.
            rest_stripped = rest.strip()
            if rest_stripped[:1] in "|>":
                indicator = rest_stripped[0]
                k = i + 1
                block_lines: list[str] = []
                while k < len(lines):
                    bline = lines[k]
                    if not bline.strip():
                        block_lines.append("")
                        k += 1
                        continue
                    bleading = len(bline) - len(bline.lstrip(" "))
                    if bleading <= indent:
                        k += 1
                        break
                    block_lines.append(bline)
                    k += 1
                if block_lines:
                    pad = min(
                        (len(bl) - len(bl.lstrip(" ")))
                        for bl in block_lines
                        if bl.strip()
                    )
                    pad = max(pad, indent + 1)
                    block_lines = [
                        (bl[pad:] if bl.strip() else "") for bl in block_lines
                    ]
                value = "\n".join(block_lines)
                if indicator == ">":
                    value = _fold_block_text(value)
                result[key] = value
                i = k
                continue
            result[key] = _coerce_scalar(rest)
            i += 1
            continue
        # Value starts on subsequent lines.
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines):
            result[key] = None
            i += 1
            continue
        next_line = lines[j]
        next_leading = len(next_line) - len(next_line.lstrip(" "))
        if next_leading <= indent:
            result[key] = None
            i += 1
            continue
        next_content = next_line[next_leading:]
        if next_content.startswith("- "):
            # Sequence — consume every ``- item`` line at deeper indent.
            items: list[object] = []
            k = i + 1
            while k < len(lines):
                cur = lines[k]
                if not cur.strip():
                    k += 1
                    continue
                cur_leading = len(cur) - len(cur.lstrip(" "))
                if cur_leading <= indent:
                    # Sequence ended; also advance past the terminator.
                    k += 1
                    break
                if cur_leading != next_leading:
                    # Mismatched indent — skip gracefully.
                    k += 1
                    continue
                cur_content = cur[cur_leading:]
                if not cur_content.startswith("- "):
                    k += 1
                    break
                items.append(_coerce_scalar(cur_content[2:]))
                k += 1
            result[key] = items
            i = k
            continue
        if next_content[0] in "|>":
            # Block scalar.
            block_lines: list[str] = []
            k = j + 1
            while k < len(lines):
                bline = lines[k]
                if not bline.strip():
                    block_lines.append("")
                    k += 1
                    continue
                bleading = len(bline) - len(bline.lstrip(" "))
                if bleading <= indent:
                    k += 1
                    break
                block_lines.append(bline)
                k += 1
            if block_lines:
                pad = min(
                    (len(bl) - len(bl.lstrip(" ")))
                    for bl in block_lines
                    if bl.strip()
                )
                pad = max(pad, indent + 1)
                block_lines = [
                    (bl[pad:] if bl.strip() else "") for bl in block_lines
                ]
            value = "\n".join(block_lines)
            if next_content[0] == ">":
                value = _fold_block_text(value)
            result[key] = value
            i = k
            continue
        if re.match(r"^[A-Za-z_][\w-]*\s*:", next_content):
            # Nested mapping.
            sub = _parse_yaml_mapping("\n".join(lines[j:]), next_leading)
            result[key] = sub
            k = j
            while k < len(lines):
                cur = lines[k]
                if not cur.strip():
                    k += 1
                    continue
                cur_leading = len(cur) - len(cur.lstrip(" "))
                if cur_leading < next_leading:
                    break
                k += 1
            i = k
            continue
        # Unknown shape — scalar on next line.
        result[key] = _coerce_scalar(next_content)
        i = j + 1
    return result


def parse_skill_frontmatter(
    content: str,
) -> tuple[dict[str, object], str]:
    """Parse a SKILL.md file into ``(frontmatter_dict, body_text)``.

    Returns an empty dict (with a warning logged) for files that do not
    begin with a ``---`` frontmatter block or whose YAML is malformed.  The
    body text is always the markdown portion after the closing ``---``.
    """

    if not content.startswith("---"):
        return {}, content

    m = _FRONTMATTER_RE.match(content)
    if m is None:
        # Unterminated frontmatter — treat the whole file as body.
        return {}, content

    fm_text = m.group(1)
    body = m.group(2).lstrip("\n")
    # Minimal-YAML parser starting at indentation 0.
    try:
        fm = _parse_yaml_mapping(fm_text, indent=0)
    except _YAMLError:
        return {}, body
    except Exception:
        # Defensive: never let parser failures bubble up.
        return {}, body
    if not isinstance(fm, dict):
        fm = {}
    return fm, body


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SkillMetadata:
    """Lightweight skill descriptor — returned by Tier-1 listing APIs."""

    name: str
    description: str
    category: str = "general"
    version: str = "1.0.0"
    source: str = "builtin"
    usage_count: int = 0
    last_used: float = 0.0
    created_by: str | None = None
    related_skills: list[str] = field(default_factory=list)
    path: Path | None = None

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------
    def bump_usage(self) -> None:
        self.usage_count += 1
        self.last_used = time.time()


@dataclass(slots=True)
class SkillContent:
    """Full skill bundle — returned by Tier-2 :meth:`SkillRegistry.load_skill`."""

    metadata: SkillMetadata
    body: str
    references: dict[str, str] = field(default_factory=dict)
    templates: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SkillRegistry
# ---------------------------------------------------------------------------

class SkillRegistry:
    """Two-tier skill discovery and loading registry.

    Typical lifecycle
    -----------------
    1. Construct a registry (optionally pre-populate with ``skill_roots``).
    2. Call :meth:`discover_skills` to scan disk once (Tier 1).
    3. Use :meth:`list_skills` / :meth:`search_skills` to render listings.
    4. Call :meth:`load_skill` (Tier 2) only when the LLM indicates interest.

    Thread safety: the registry is *not* thread-safe by design — skill
    disclosure is a request-scoped concern and callers are expected to
    construct a fresh registry per session.
    """

    def __init__(self, skill_roots: Iterable[Path] | None = None) -> None:
        self._metadata: dict[str, SkillMetadata] = {}
        # Cache Tier-2 loads to avoid re-reading disk within one request.
        self._content_cache: dict[str, SkillContent] = {}
        if skill_roots:
            self.discover_skills(skill_roots)

    # ------------------------------------------------------------------
    # Discovery (Tier 1)
    # ------------------------------------------------------------------
    def discover_skills(self, skill_roots: Iterable[Path]) -> int:
        """Scan *skill_roots* for SKILL.md files and register their metadata.

        Returns the number of skills newly discovered (skipping duplicates
        and files that are already registered).
        """

        added = 0
        seen_paths: set[Path] = set(self._unique_skill_paths())
        for root in skill_roots:
            root_p = Path(root).expanduser().resolve()
            if not root_p.is_dir():
                continue
            for candidate in self._iter_candidate_files(root_p):
                if candidate in seen_paths:
                    continue
                seen_paths.add(candidate)
                meta = self._load_metadata_only(candidate)
                if meta is None:
                    continue
                if self._is_unsupported_platform(meta):
                    continue
                if meta.name in self._metadata:
                    continue
                self._metadata[meta.name] = meta
                added += 1
        return added

    def _unique_skill_paths(self) -> Iterable[Path]:
        return (m.path for m in self._metadata.values() if m.path is not None)

    @staticmethod
    def _iter_candidate_files(root: Path) -> Iterator[Path]:
        """Yield SKILL.md paths under *root*, skipping excluded dirs."""

        for skill_name in _SKILL_MD_NAMES:
            for path in root.rglob(skill_name):
                if not path.is_file():
                    continue
                if any(
                    part in EXCLUDED_DIR_NAMES for part in path.parts
                ):
                    continue
                yield path

    @staticmethod
    def _peek_has_frontmatter(path: Path) -> bool:
        """Cheap prefilter: does the file open with ``---``?"""

        try:
            with path.open("rb") as f:
                head = f.read(_PEEK_BYTES)
        except OSError:
            return False
        return head.startswith(b"---")

    def _load_metadata_only(self, path: Path) -> SkillMetadata | None:
        if not self._peek_has_frontmatter(path):
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        fm, _ = parse_skill_frontmatter(text)
        if not fm:
            return None
        name = str(fm.get("name") or path.parent.name or path.stem)
        description = str(fm.get("description") or "")
        category = str(fm.get("category") or "general")
        version = str(fm.get("version") or "1.0.0")
        source = str(fm.get("source") or "builtin")
        created_by = fm.get("created_by")
        related = fm.get("related_skills") or []
        if isinstance(related, str):
            related_list = [related] if related else []
        elif isinstance(related, list):
            related_list = [str(r) for r in related]
        else:
            related_list = []
        return SkillMetadata(
            name=name,
            description=description,
            category=category,
            version=version,
            source=source,
            created_by=str(created_by) if created_by is not None else None,
            related_skills=related_list,
            path=path,
        )

    @staticmethod
    def _is_unsupported_platform(meta: SkillMetadata) -> bool:
        """Return ``True`` if the skill targets a platform other than current."""

        if meta.path is None:
            return False
        try:
            text = meta.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return False
        m = _FRONTMATTER_RE.match(text)
        if m is None:
            return False
        fm_text = m.group(1)
        # Platform line may be a scalar or a list.  Do a quick line scan.
        for line in fm_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("platform:"):
                value = stripped[len("platform:"):].strip()
                if value.startswith("[") and value.endswith("]"):
                    tokens = [t.strip().strip('"').strip("'") for t in value[1:-1].split(",")]
                else:
                    tokens = [value.strip('"').strip("'")]
                tokens = [t for t in tokens if t]
                if tokens and _PLATFORM_TOKEN not in tokens:
                    return True
                return False
        return False

    # ------------------------------------------------------------------
    # Tier-1 listing
    # ------------------------------------------------------------------
    def list_skills(
        self,
        category: str | None = None,
        source: str | None = None,
    ) -> list[SkillMetadata]:
        out: list[SkillMetadata] = []
        for meta in self._metadata.values():
            if category is not None and meta.category != category:
                continue
            if source is not None and meta.source != source:
                continue
            out.append(meta)
        out.sort(key=lambda m: m.name.lower())
        return out

    def categories(self) -> list[str]:
        return sorted({m.category for m in self._metadata.values()})

    def get_skill_metadata(self, skill_name: str) -> SkillMetadata | None:
        return self._metadata.get(skill_name)

    # ------------------------------------------------------------------
    # Tier-2 loading
    # ------------------------------------------------------------------
    def load_skill(self, skill_name: str) -> SkillContent | None:
        if skill_name in self._content_cache:
            # Bump usage on every load — even cached ones.
            self._content_cache[skill_name].metadata.bump_usage()
            return self._content_cache[skill_name]

        meta = self._metadata.get(skill_name)
        if meta is None or meta.path is None:
            return None

        try:
            text = meta.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

        fm, body = parse_skill_frontmatter(text)
        references = self._collect_supporting_files(meta.path, "references")
        templates = self._collect_supporting_files(meta.path, "templates")

        # Surface any frontmatter-driven overrides that influence content.
        override_meta = self._apply_content_overrides(meta, fm)
        content = SkillContent(
            metadata=override_meta,
            body=body,
            references=references,
            templates=templates,
        )
        override_meta.bump_usage()
        self._content_cache[skill_name] = content
        return content

    def load_skill_reference(
        self, skill_name: str, file_path: str
    ) -> str | None:
        """Load a single supporting file relative to a skill's directory.

        ``file_path`` may be either a bare filename (looked up in the
        ``references/`` then ``templates/`` sibling) or a subpath such as
        ``references/setup.md``.  Returns ``None`` for missing files or
        path-traversal attempts.
        """

        meta = self._metadata.get(skill_name)
        if meta is None or meta.path is None:
            return None

        skill_dir = meta.path.parent
        # Prevent traversal.
        target = (skill_dir / file_path).resolve()
        try:
            target.relative_to(skill_dir.resolve())
        except ValueError:
            return None
        if not target.is_file():
            # Fall back: maybe the caller passed a bare name.
            for sub in ("references", "templates"):
                alt = (skill_dir / sub / file_path).resolve()
                try:
                    alt.relative_to(skill_dir.resolve())
                except ValueError:
                    continue
                if alt.is_file():
                    target = alt
                    break
            else:
                return None
        try:
            return target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------
    def increment_usage(self, skill_name: str) -> None:
        meta = self._metadata.get(skill_name)
        if meta is not None:
            meta.bump_usage()
        cached = self._content_cache.get(skill_name)
        if cached is not None:
            cached.metadata.bump_usage()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def search_skills(self, query: str) -> list[SkillMetadata]:
        """Fuzzy match *query* against name / description / category."""

        q = query.strip().lower()
        if not q:
            return self.list_skills()
        scored: list[tuple[int, SkillMetadata]] = []
        for meta in self._metadata.values():
            score = self._score_match(meta, q)
            if score > 0:
                scored.append((score, meta))
        scored.sort(key=lambda t: (-t[0], t[1].name.lower()))
        return [m for _, m in scored]

    @staticmethod
    def _score_match(meta: SkillMetadata, q: str) -> int:
        score = 0
        name_l = meta.name.lower()
        desc_l = meta.description.lower()
        cat_l = meta.category.lower()
        if name_l == q:
            score += 100
        elif name_l.startswith(q):
            score += 60
        elif q in name_l:
            score += 30
        if q and q in desc_l:
            # Reward multiple word hits.
            desc_hits = desc_l.count(q)
            score += 10 + 2 * min(desc_hits, 5)
        if q and q in cat_l:
            score += 8
        for related in meta.related_skills:
            if q in related.lower():
                score += 5
        return score

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _collect_supporting_files(
        skill_file: Path, subdir: str
    ) -> dict[str, str]:
        """Return a ``{relative_path: content}`` dict for a sibling dir."""

        base = skill_file.parent
        refs_dir = base / subdir
        out: dict[str, str] = {}
        if not refs_dir.is_dir():
            return out
        for path in refs_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in _SUPPORTED_REF_SUFFIXES:
                continue
            rel = path.relative_to(refs_dir).as_posix()
            try:
                out[rel] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
        return out

    @staticmethod
    def _apply_content_overrides(
        meta: SkillMetadata, fm: dict[str, object]
    ) -> SkillMetadata:
        """Return a (possibly shallow-copied) metadata with fm-driven overrides."""

        if not fm:
            return meta
        # Only a handful of frontmatter fields should override metadata at
        # load time — the rest are set during discovery.
        updates: dict[str, object] = {}
        if "description" in fm and fm["description"]:
            updates["description"] = str(fm["description"])
        if "version" in fm and fm["version"] not in (None, ""):
            updates["version"] = str(fm["version"])
        if not updates:
            return meta
        return SkillMetadata(
            name=meta.name,
            description=str(updates.get("description", meta.description)),
            category=meta.category,
            version=str(updates.get("version", meta.version)),
            source=meta.source,
            usage_count=meta.usage_count,
            last_used=meta.last_used,
            created_by=meta.created_by,
            related_skills=list(meta.related_skills),
            path=meta.path,
        )
