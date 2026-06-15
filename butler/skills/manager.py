"""Butler skill lifecycle: flat `name.md` files with YAML frontmatter."""

from __future__ import annotations

import logging
import re
import shutil
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from butler.skills.consolidator import SkillConsolidator
from butler.skills.similarity import SkillSimilarity
from butler.skills.usage import UsageTracker

logger = logging.getLogger(__name__)

VALID_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
MAX_NAME_LEN = 64
MAX_DESC_LEN = 1024

_LLMFn = Optional[Callable[[str], str]]

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)
_MetadataSignature = tuple[int, int]


# ---------------------------------------------------------------------------
# Audit R2-8: skill load error disambiguation + recent-errors buffer.
#
# Before this commit, ``_read_frontmatter_only`` reported three distinct
# failure modes (no opening ``---``, unterminated frontmatter, invalid UTF-8,
# OSError) with the SAME warning message, so operators could not tell *why*
# a skill file failed to load. We expose a categorized ``SkillLoadError``
# exception plus a small thread-safe buffer so ``/诊断`` (and any future
# prompt-side health reporting) can aggregate recent load failures.
# ---------------------------------------------------------------------------

# Stable error codes — keep in sync with tests/test_r2_8_skill_load_error.py
# and tests/test_r2_13_skill_path_traversal.py
SKILL_LOAD_ERR_NO_FRONTMATTER = "no_frontmatter"
SKILL_LOAD_ERR_UNTERMINATED = "unterminated_frontmatter"
SKILL_LOAD_ERR_ENCODING = "frontmatter_encoding"
SKILL_LOAD_ERR_IO = "skill_io_error"
SKILL_LOAD_ERR_PATH_TRAVERSAL = "path_traversal_attempt"

_SKILL_LOAD_ERROR_BUFFER_MAX = 64
_SKILL_LOAD_ERROR_BUFFER_LOCK = threading.RLock()
_RECENT_SKILL_LOAD_ERRORS: list[SkillLoadError] = []  # populated below


class SkillLoadError(Exception):
    """Categorized skill load failure for /诊断 aggregation (audit R2-8)."""

    code: str
    path: Path
    message: str

    def __init__(self, code: str, path: Path, message: str) -> None:
        super().__init__(message)
        self.code = str(code)
        self.path = path
        self.message = str(message)


def _record_skill_load_error(code: str, path: Path, message: str) -> SkillLoadError:
    """Append a categorized error to the recent-errors buffer (thread-safe)."""
    err = SkillLoadError(code=code, path=path, message=message)
    with _SKILL_LOAD_ERROR_BUFFER_LOCK:
        _RECENT_SKILL_LOAD_ERRORS.append(err)
        if len(_RECENT_SKILL_LOAD_ERRORS) > _SKILL_LOAD_ERROR_BUFFER_MAX:
            del _RECENT_SKILL_LOAD_ERRORS[
                : len(_RECENT_SKILL_LOAD_ERRORS) - _SKILL_LOAD_ERROR_BUFFER_MAX
            ]
    return err


def recent_skill_load_errors(limit: int = 20) -> list[SkillLoadError]:
    """Return the most recent N categorized skill load errors (audit R2-8)."""
    if limit <= 0:
        return []
    with _SKILL_LOAD_ERROR_BUFFER_LOCK:
        if limit >= len(_RECENT_SKILL_LOAD_ERRORS):
            return list(_RECENT_SKILL_LOAD_ERRORS)
        return list(_RECENT_SKILL_LOAD_ERRORS[-limit:])


def _clear_recent_skill_load_errors() -> None:
    """Reset the recent-errors buffer. Test-only / process-start helper."""
    with _SKILL_LOAD_ERROR_BUFFER_LOCK:
        _RECENT_SKILL_LOAD_ERRORS.clear()


def _validate_name(name: str) -> Optional[str]:
    if not name:
        return "Skill name is required."
    if len(name) > MAX_NAME_LEN:
        return f"Skill name exceeds {MAX_NAME_LEN} characters."
    if not VALID_NAME_RE.match(name):
        return (
            "Invalid skill name — use lowercase letters, digits, dots, hyphens, "
            "underscores; must start with a letter or digit."
        )
    return None


def _preferred_tools_from_fm(fm: dict[str, Any]) -> list[str]:
    pt = fm.get("preferred_tools") or []
    if isinstance(pt, str):
        return [pt.strip()] if pt.strip() else []
    if isinstance(pt, list):
        return [str(t).strip() for t in pt if str(t).strip()]
    return []


def _parse_skill_md(text: str, path: Path, source: str) -> Optional[dict[str, Any]]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        # Audit R2-8 (bonus): this regex miss means the file either has no
        # frontmatter block at all OR the block is malformed (e.g. closing
        # ``---`` missing or trailing whitespace mismatch). The previous
        # message was identical to the no-opener case in
        # ``_read_frontmatter_only`` and gave operators no way to tell them
        # apart. Return contract (None) is unchanged.
        logger.warning(
            "Skill file missing or malformed YAML frontmatter (regex match failed): %s",
            path,
        )
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        logger.warning("Bad YAML frontmatter in %s: %s", path, e)
        return None
    if not isinstance(fm, dict):
        return None
    body = m.group(2).lstrip("\n")
    name = str(fm.get("name") or path.stem)
    triggers = fm.get("triggers") or []
    if isinstance(triggers, str):
        triggers = [triggers]
    triggers = [str(t) for t in triggers]
    out: dict[str, Any] = {
        "name": name,
        "description": str(fm.get("description", "")),
        "triggers": triggers,
        "version": fm.get("version", 1),
        "created": str(fm.get("created", "")),
        "content": body,
        "_path": path,
        "_source": source,
    }
    pt = _preferred_tools_from_fm(fm)
    if pt:
        out["preferred_tools"] = pt
    return out


def _parse_skill_frontmatter(frontmatter: str, path: Path, source: str) -> Optional[dict[str, Any]]:
    try:
        fm = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError as e:
        logger.warning("Bad YAML frontmatter in %s: %s", path, e)
        return None
    if not isinstance(fm, dict):
        return None
    name = str(fm.get("name") or path.stem)
    triggers = fm.get("triggers") or []
    if isinstance(triggers, str):
        triggers = [triggers]
    triggers = [str(t) for t in triggers]
    out: dict[str, Any] = {
        "name": name,
        "description": str(fm.get("description", "")),
        "triggers": triggers,
        "version": fm.get("version", 1),
        "created": str(fm.get("created", "")),
        "_path": path,
        "_source": source,
    }
    if str(fm.get("install_type") or "") == "directory":
        out["install_type"] = "directory"
        out["content_path"] = str(fm.get("content_path") or "")
    pt = _preferred_tools_from_fm(fm)
    if pt:
        out["preferred_tools"] = pt
    return out


def _read_frontmatter_only(path: Path) -> Optional[str]:
    # Audit R2-8: three distinct failure modes (no opener, unterminated,
    # encoding error) plus an OSError path used to all log the same warning.
    # Now each branch logs a distinct message; the two ``except`` sites log
    # at ERROR with ``exc_info``; and every failure appends a categorized
    # ``SkillLoadError`` to the module-level recent-errors buffer for /诊断.
    try:
        with path.open("rb") as f:
            first = f.readline()
            if first.strip() != b"---":
                msg = f"Skill file has no YAML frontmatter opener (---): {path}"
                logger.warning(msg)
                _record_skill_load_error(
                    SKILL_LOAD_ERR_NO_FRONTMATTER, path, msg
                )
                return None
            lines: list[bytes] = []
            for line in f:
                if line.strip() == b"---":
                    return b"".join(lines).decode("utf-8")
                lines.append(line)
    except UnicodeDecodeError as exc:
        msg = f"Skill file frontmatter has invalid UTF-8 encoding: {path}"
        logger.error(msg, exc_info=exc)
        _record_skill_load_error(SKILL_LOAD_ERR_ENCODING, path, msg)
        return None
    except OSError as exc:
        msg = f"Skill file could not be opened: {path}"
        logger.error(msg, exc_info=exc)
        _record_skill_load_error(SKILL_LOAD_ERR_IO, path, msg)
        return None

    # Fallthrough: file started with ``---`` but never closed the block.
    msg = f"Skill file has unterminated YAML frontmatter (no closing ---): {path}"
    logger.warning(msg)
    _record_skill_load_error(SKILL_LOAD_ERR_UNTERMINATED, path, msg)
    return None


def _render_skill_md(skill: dict[str, Any]) -> str:
    fm = {
        "name": skill["name"],
        "description": skill["description"],
        "triggers": list(skill.get("triggers") or []),
        "version": int(skill.get("version", 1) or 1),
        "created": str(skill.get("created", date.today().isoformat())),
    }
    body = str(skill.get("content", skill.get("body", "")))
    fm_yaml = yaml.safe_dump(
        fm,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).strip()
    return f"---\n{fm_yaml}\n---\n{body}"


class SkillManager:
    """Manage `name.md` skills under *skills_dir* with optional global overlay."""

    def __init__(
        self,
        skills_dir: str | Path,
        global_skills_dir: str | Path | None = None,
        llm_fn: _LLMFn = None,
    ) -> None:
        self._skills_dir = Path(skills_dir)
        self._global_skills_dir = Path(global_skills_dir) if global_skills_dir else None
        self._skills_dir.mkdir(parents=True, exist_ok=True)
        if self._global_skills_dir is not None:
            self._global_skills_dir.mkdir(parents=True, exist_ok=True)

        self._usage = UsageTracker(self._skills_dir / ".butler_skill_usage.json")
        self._similarity = SkillSimilarity(llm_fn=llm_fn)
        self._consolidator = SkillConsolidator(llm_fn=llm_fn)
        self._metadata_cache: dict[tuple[str, str], tuple[_MetadataSignature, dict[str, Any]]] = {}
        # Sprint 20-4 PERF-20-C-1: full-skill cache keyed by (path, source) +
        # (mtime_ns, size) signature. Mirrors _metadata_cache but stores the
        # full body parsed by _load_skill_from_path. Eliminates the N+1
        # read_text + yaml.safe_load in get_skill / get_skills / list_skills
        # when the same skill is touched multiple times within an LLM turn.
        self._full_cache: dict[tuple[str, str], tuple[_MetadataSignature, dict[str, Any]]] = {}

    def set_llm_fn(self, fn: _LLMFn) -> None:
        self._similarity.set_llm_fn(fn)
        self._consolidator.set_llm_fn(fn)

    def _archive_path(self) -> Path:
        p = self._skills_dir / ".archive"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _archive_file(self, path: Path) -> None:
        if not path.is_file():
            return
        dest_dir = self._archive_path()
        ts = int(time.time())
        dest = dest_dir / f"{path.stem}_{ts}.md"
        shutil.move(str(path), str(dest))
        logger.info("Archived skill file %s -> %s", path, dest)

    def _skills_root_for(self, path: Path, source: str) -> Path:
        if source == "global" and self._global_skills_dir is not None:
            return self._global_skills_dir
        return self._skills_dir

    def _iter_skill_files(self) -> list[tuple[Path, str]]:
        from butler.skills.layout import iter_skill_entry_paths

        out: list[tuple[Path, str]] = []
        if self._global_skills_dir is not None:
            for entry in iter_skill_entry_paths(self._global_skills_dir):
                out.append((entry.path, "global"))
        for entry in iter_skill_entry_paths(self._skills_dir):
            if entry.path.parent.name == ".archive":
                continue
            out.append((entry.path, "project"))
        return out

    def _apply_directory_content(
        self,
        sk: dict[str, Any],
        fm: dict[str, Any],
        rel: str,
        path: Path,
        source: str,
    ) -> dict[str, Any]:
        """Merge inner content into ``sk`` for ``install_type: directory``.

        Audit R2-13: a ``content_path`` that escapes the skills root is a
        security signal — log at ERROR with full traceback and append a
        categorized ``SkillLoadError`` so /诊断 can aggregate traversal
        attempts. Behaviour change: still return ``sk`` unchanged (skill
        remains usable) but the inner content is dropped — same as before,
        just no longer silent.
        """
        root = self._skills_root_for(path, source)
        content_path = (root / rel).resolve()
        try:
            content_path.relative_to(root.resolve())
        except ValueError as exc:
            msg = f"Skill content_path escapes skills root (security signal): {rel} in {path}"
            logger.error(msg, exc_info=exc)
            _record_skill_load_error(SKILL_LOAD_ERR_PATH_TRAVERSAL, path, msg)
            return sk
        if not content_path.is_file():
            return sk
        inner = _parse_skill_md(
            content_path.read_text(encoding="utf-8"),
            content_path,
            source,
        )
        if not inner:
            return sk
        sk["description"] = str(fm.get("description") or inner.get("description") or "")
        sk["triggers"] = inner.get("triggers") or sk.get("triggers") or []
        sk["content"] = inner.get("content") or ""
        sk["_content_path"] = content_path
        inner_pt = inner.get("preferred_tools")
        if inner_pt:
            sk["preferred_tools"] = inner_pt
        return sk

    def _merge_directory_metadata(
        self,
        sk: dict[str, Any],
        fm: dict[str, Any],
        rel: str,
        path: Path,
        source: str,
    ) -> dict[str, Any]:
        """Merge triggers/preferred_tools from inner SKILL.md for list_skills."""
        root = self._skills_root_for(path, source)
        content_path = (root / rel).resolve()
        try:
            content_path.relative_to(root.resolve())
        except ValueError:
            return sk
        if not content_path.is_file():
            return sk
        inner_fm_text = _read_frontmatter_only(content_path)
        if not inner_fm_text:
            return sk
        inner_sk = _parse_skill_frontmatter(inner_fm_text, content_path, source)
        if not inner_sk:
            return sk
        sk["description"] = str(
            fm.get("description") or inner_sk.get("description") or sk.get("description") or ""
        )
        sk["triggers"] = inner_sk.get("triggers") or sk.get("triggers") or []
        inner_pt = inner_sk.get("preferred_tools")
        if inner_pt:
            sk["preferred_tools"] = inner_pt
        elif sk.get("preferred_tools"):
            pass
        return sk

    def _load_skill_from_path(self, path: Path, source: str) -> Optional[dict[str, Any]]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Could not read %s: %s", path, e)
            return None
        sk = _parse_skill_md(text, path, source)
        if not sk:
            return None
        fm_text = _read_frontmatter_only(path)
        if not fm_text:
            return sk
        try:
            fm = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError:
            fm = {}
        if not (isinstance(fm, dict) and str(fm.get("install_type") or "") == "directory"):
            return sk
        rel = str(fm.get("content_path") or "").strip()
        if not rel:
            return sk
        return self._apply_directory_content(sk, fm, rel, path, source)

    def _load_all(self) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        active_keys: set[tuple[str, str]] = set()
        for path, source in self._iter_skill_files():
            active_keys.add((str(path), source))
            sk = self._load_full_cached(path, source)
            if not sk:
                continue
            name = sk["name"]
            if name not in seen:
                order.append(name)
            # Project shadows global for the same skill name.
            if name in seen and source == "global" and seen[name].get("_source") == "project":
                continue
            seen[name] = sk
        # Evict cache entries for files that no longer exist (mirror _load_metadata_all).
        for key in list(self._full_cache):
            if key not in active_keys:
                self._full_cache.pop(key, None)
        return [seen[k] for k in order if k in seen]

    def _load_full_cached(self, path: Path, source: str) -> Optional[dict[str, Any]]:
        """Sprint 20-4 PERF-20-C-1: mtime/size-keyed full-skill cache.

        Same invalidation contract as ``_load_metadata``: the cached dict
        is only returned when the file's ``(st_mtime_ns, st_size)`` matches
        the recorded signature. Returns a shallow copy so callers can mutate
        the result without corrupting the cache.
        """
        sig = self._metadata_signature(path)
        if sig is None:
            return None

        key = (str(path), source)
        cached = self._full_cache.get(key)
        if cached and cached[0] == sig:
            return dict(cached[1])

        sk = self._load_skill_from_path(path, source)
        if not sk:
            self._full_cache.pop(key, None)
            return None

        self._full_cache[key] = (sig, dict(sk))
        return sk

    def _metadata_signature(self, path: Path) -> _MetadataSignature | None:
        try:
            st = path.stat()
        except OSError as e:
            logger.warning("Could not stat %s: %s", path, e)
            return None
        return (st.st_mtime_ns, st.st_size)

    def _load_metadata(self, path: Path, source: str) -> Optional[dict[str, Any]]:
        sig = self._metadata_signature(path)
        if sig is None:
            return None

        key = (str(path), source)
        cached = self._metadata_cache.get(key)
        if cached and cached[0] == sig:
            return dict(cached[1])

        frontmatter = _read_frontmatter_only(path)
        if frontmatter is None:
            self._metadata_cache.pop(key, None)
            return None

        sk = _parse_skill_frontmatter(frontmatter, path, source)
        if not sk:
            self._metadata_cache.pop(key, None)
            return None

        if sk.get("install_type") == "directory":
            try:
                fm = yaml.safe_load(frontmatter) or {}
            except yaml.YAMLError:
                fm = {}
            rel = str((fm if isinstance(fm, dict) else {}).get("content_path") or "").strip()
            if rel:
                sk = self._merge_directory_metadata(sk, fm if isinstance(fm, dict) else {}, rel, path, source)

        self._metadata_cache[key] = (sig, dict(sk))
        return sk

    def _load_metadata_all(self) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        active_keys: set[tuple[str, str]] = set()
        for path, source in self._iter_skill_files():
            active_keys.add((str(path), source))
            sk = self._load_metadata(path, source)
            if not sk:
                continue
            name = sk["name"]
            if name not in seen:
                order.append(name)
            # Project shadows global for the same skill name.
            if name in seen and source == "global" and seen[name].get("_source") == "project":
                continue
            seen[name] = sk

        for key in list(self._metadata_cache):
            if key not in active_keys:
                self._metadata_cache.pop(key, None)
        return [seen[k] for k in order if k in seen]

    def list_skills(self) -> list[dict[str, Any]]:
        """Metadata summaries (no full body)."""
        summaries: list[dict[str, Any]] = []
        for sk in self._load_metadata_all():
            item: dict[str, Any] = {
                "name": sk["name"],
                "description": sk.get("description", ""),
                "triggers": list(sk.get("triggers") or []),
                "version": sk.get("version", 1),
                "created": sk.get("created", ""),
                "source": sk.get("_source", "project"),
            }
            pt = sk.get("preferred_tools")
            if pt:
                item["preferred_tools"] = list(pt)
            summaries.append(item)
        return summaries

    def get_skill(self, name: str) -> Optional[dict[str, Any]]:
        for sk in self._load_all():
            if sk.get("name") == name:
                self._usage.on_view(name)
                out = {k: v for k, v in sk.items() if not str(k).startswith("_")}
                return out
        return None

    def get_skills(self, names: list[str]) -> dict[str, dict[str, Any]]:
        wanted = {str(name) for name in names if str(name)}
        if not wanted:
            return {}

        found: dict[str, dict[str, Any]] = {}
        for sk in self._load_all():
            name = str(sk.get("name", ""))
            if name in wanted:
                self._usage.on_view(name)
                found[name] = {k: v for k, v in sk.items() if not str(k).startswith("_")}
        return found

    def create(
        self,
        name: str,
        description: str,
        triggers: list[str],
        content: str,
        *,
        similarity_threshold: float = 0.6,
    ) -> str:
        """Return ``\"created\"`` or ``\"merged\"``."""
        err = _validate_name(name)
        if err:
            raise ValueError(err)

        from butler.skills.guard import scan_skill_text
        guard_issues = scan_skill_text(content)
        if guard_issues:
            raise ValueError(f"Skill content failed security scan: {', '.join(guard_issues)}")
        if not description:
            raise ValueError("Description is required.")
        if len(description) > MAX_DESC_LEN:
            raise ValueError(f"Description exceeds {MAX_DESC_LEN} characters.")
        if not content or not str(content).strip():
            raise ValueError("Content is required.")

        today = date.today().isoformat()
        new_skill: dict[str, Any] = {
            "name": name,
            "description": description.strip(),
            "triggers": [str(t).strip() for t in triggers if str(t).strip()],
            "version": 1,
            "created": today,
            "content": content,
        }

        existing = self._load_all()
        stripped = [{k: v for k, v in s.items() if not str(k).startswith("_")} for s in existing]

        similar = self._similarity.find_similar(new_skill, stripped, threshold=similarity_threshold)

        if similar:
            to_merge_raw = [new_skill] + [s for s, _ in similar]
            merged = self._consolidator.consolidate(to_merge_raw)
            if merged.get("fallback_used"):
                try:
                    from butler.ops.runtime_metrics import inc

                    inc("digestion_skill_fallback_merge")
                except Exception:
                    pass

            old_names = {s["name"] for s in to_merge_raw if s.get("name")}
            for sk in existing:
                if sk.get("name") in old_names and isinstance(sk.get("_path"), Path):
                    self._archive_file(sk["_path"])

            out_path = self._skills_dir / f"{merged['name']}.md"
            if out_path.exists():
                self._archive_file(out_path)

            merged.setdefault("created", today)
            merged.setdefault("version", 1)
            out_path.write_text(_render_skill_md(merged), encoding="utf-8")

            self._usage.on_merge(list(old_names), merged["name"])
            self._usage.on_create(merged["name"])

            logger.info("Merged skills %s -> %s", sorted(old_names), merged["name"])
            return "merged"

        dest = self._skills_dir / f"{name}.md"
        if dest.exists():
            raise ValueError(f"Skill '{name}' already exists.")

        dest.write_text(_render_skill_md(new_skill), encoding="utf-8")
        self._usage.on_create(name)
        logger.info("Created skill '%s'", name)
        return "created"

    def edit(self, name: str, content: str) -> None:
        sk = None
        for s in self._load_all():
            if s.get("name") == name:
                sk = s
                break
        if not sk:
            raise ValueError(f"Skill '{name}' not found.")

        path = sk.get("_path")
        if not isinstance(path, Path):
            raise ValueError(f"Skill '{name}' has no writable path.")

        text = path.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(text)
        if not m:
            raise ValueError(f"Skill '{name}' is missing YAML frontmatter.")
        new_text = f"---\n{m.group(1)}\n---\n{content.lstrip()}"
        path.write_text(new_text, encoding="utf-8")
        logger.info("Edited skill '%s'", name)

    def delete(self, name: str) -> None:
        sk = None
        for s in self._load_all():
            if s.get("name") == name:
                sk = s
                break
        if not sk:
            raise ValueError(f"Skill '{name}' not found.")
        path = sk.get("_path")
        if isinstance(path, Path) and path.is_file():
            self._archive_file(path)
        self._usage.on_delete(name)
        logger.info("Deleted skill '%s'", name)
