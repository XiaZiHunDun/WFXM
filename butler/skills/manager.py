"""Butler skill lifecycle: flat `name.md` files with YAML frontmatter."""

from __future__ import annotations

import logging
import re
import shutil
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


def _parse_skill_md(text: str, path: Path, source: str) -> Optional[dict[str, Any]]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        logger.warning("Skill file missing YAML frontmatter: %s", path)
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
    return {
        "name": name,
        "description": str(fm.get("description", "")),
        "triggers": triggers,
        "version": fm.get("version", 1),
        "created": str(fm.get("created", "")),
        "content": body,
        "_path": path,
        "_source": source,
    }


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
    return {
        "name": name,
        "description": str(fm.get("description", "")),
        "triggers": triggers,
        "version": fm.get("version", 1),
        "created": str(fm.get("created", "")),
        "_path": path,
        "_source": source,
    }


def _read_frontmatter_only(path: Path) -> Optional[str]:
    try:
        with path.open("rb") as f:
            first = f.readline()
            if first.strip() != b"---":
                logger.warning("Skill file missing YAML frontmatter: %s", path)
                return None
            lines: list[bytes] = []
            for line in f:
                if line.strip() == b"---":
                    return b"".join(lines).decode("utf-8")
                lines.append(line)
    except UnicodeDecodeError as e:
        logger.warning("Bad YAML frontmatter encoding in %s: %s", path, e)
        return None
    except OSError as e:
        logger.warning("Could not read %s: %s", path, e)
        return None

    logger.warning("Skill file missing YAML frontmatter: %s", path)
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

    def _iter_skill_files(self) -> list[tuple[Path, str]]:
        out: list[tuple[Path, str]] = []
        if self._global_skills_dir is not None:
            for p in sorted(self._global_skills_dir.glob("*.md")):
                if p.name.startswith("."):
                    continue
                out.append((p, "global"))
        for p in sorted(self._skills_dir.glob("*.md")):
            if p.name.startswith(".") or p.parent.name == ".archive":
                continue
            out.append((p, "project"))
        return out

    def _load_all(self) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for path, source in self._iter_skill_files():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as e:
                logger.warning("Could not read %s: %s", path, e)
                continue
            sk = _parse_skill_md(text, path, source)
            if not sk:
                continue
            name = sk["name"]
            if name not in seen:
                order.append(name)
            # Project shadows global for the same skill name.
            if name in seen and source == "global" and seen[name].get("_source") == "project":
                continue
            seen[name] = sk
        return [seen[k] for k in order if k in seen]

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
            summaries.append(
                {
                    "name": sk["name"],
                    "description": sk.get("description", ""),
                    "triggers": list(sk.get("triggers") or []),
                    "version": sk.get("version", 1),
                    "created": sk.get("created", ""),
                    "source": sk.get("_source", "project"),
                }
            )
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
