from __future__ import annotations

import logging
import shutil
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional, cast

import yaml  # type: ignore[import-untyped]

from butler.skills.consolidator import SkillConsolidator
from butler.skills.similarity import SkillSimilarity
from butler.skills.usage import UsageTracker

from .constants import _FRONTMATTER_RE, MAX_DESC_LEN
from .errors import _record_skill_load_error, SKILL_LOAD_ERR_IO, SKILL_LOAD_ERR_PATH_TRAVERSAL
from .parsing import _parse_skill_frontmatter, _parse_skill_md, _read_frontmatter_only, _render_skill_md, _validate_name

logger = logging.getLogger(__name__)

_LLMFn = Optional[Callable[[str], str]]
_MetadataSignature = tuple[int, int]


class SkillManager:
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

    def _apply_load_policy(
        self, sk: dict[str, Any], path: Path, source: str
    ) -> Optional[dict[str, Any]]:
        from butler.skills.manager_ops import enrich_skill_load_policy_safe

        def _record_block(msg: str) -> None:
            logger.warning(msg)
            _record_skill_load_error(SKILL_LOAD_ERR_IO, path, msg)

        return cast(
            dict[str, Any] | None,
            enrich_skill_load_policy_safe(
                sk,
                path,
                source,
                record_block=_record_block,
            ),
        )

    def _load_skill_from_path(self, path: Path, source: str) -> Optional[dict[str, Any]]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Could not read %s: %s", path, e)
            return None
        sk = _parse_skill_md(text, path, source)
        if not sk:
            return None
        sk = self._apply_load_policy(sk, path, source)
        if sk is None:
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
            if name in seen and source == "global" and seen[name].get("_source") == "project":
                continue
            seen[name] = sk
        for key in list(self._full_cache):
            if key not in active_keys:
                self._full_cache.pop(key, None)
        return [seen[k] for k in order if k in seen]

    def _load_full_cached(self, path: Path, source: str) -> Optional[dict[str, Any]]:
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

        sk = self._apply_load_policy(sk, path, source)
        if sk is None:
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
            if name in seen and source == "global" and seen[name].get("_source") == "project":
                continue
            seen[name] = sk

        for key in list(self._metadata_cache):
            if key not in active_keys:
                self._metadata_cache.pop(key, None)
        return [seen[k] for k in order if k in seen]

    def list_skills(self) -> list[dict[str, Any]]:
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
        _bypass_approval: bool = False,
    ) -> str:
        err = _validate_name(name)
        if err:
            raise ValueError(err)

        if not _bypass_approval:
            from butler.skills.manager_ops import maybe_queue_skill_pending_safe

            pending = maybe_queue_skill_pending_safe(
                name=name,
                description=description,
                triggers=triggers,
                content=content,
            )
            if pending == "pending":
                return "pending"

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
                from butler.skills.manager_ops import record_skill_merge_fallback_safe

                record_skill_merge_fallback_safe()

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