"""Claude Code marketplace.json adapter (REG-P2)."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml

from butler.registry.paths import catalog_dir
from butler.registry.skill_sources.base import SkillSource
from butler.registry.skill_sources.github import GitHubSource
from butler.registry.skill_types import SkillBundle, SkillSearchHit
from butler.registry.url_safety import is_safe_url

logger = logging.getLogger(__name__)

_ALLOWED_SUFFIXES = (".md", ".txt", ".json", ".yaml", ".yml")


def marketplace_enabled() -> bool:
    return os.getenv("BUTLER_CLAUDE_MARKETPLACE_ENABLED", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


@dataclass(frozen=True)
class _MarketplaceCatalog:
    id: str
    title: str
    trust: str
    base_path: Path | None
    base_raw_url: str


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", s.lower()).strip("-")[:64]


def _parse_identifier(identifier: str) -> tuple[str, str] | None:
    ident = identifier.strip()
    for prefix in ("marketplace:", "claude-marketplace:", "claude:"):
        if ident.startswith(prefix):
            ident = ident[len(prefix) :]
            break
    if "/" not in ident:
        return None
    mp_id, plugin = ident.split("/", 1)
    mp_id = mp_id.strip()
    plugin = plugin.strip()
    if not mp_id or not plugin:
        return None
    return mp_id, plugin


def _load_marketplace_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("marketplace json %s: %s", path, exc)
        return None


def _fetch_marketplace_url(url: str) -> dict[str, Any] | None:
    if not is_safe_url(url):
        return None
    try:
        from butler.registry.url_safety import safe_registry_get

        resp = safe_registry_get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.debug("marketplace url fetch %s: %s", url, exc)
        return None


def _raw_base_from_github_marketplace_url(url: str) -> str | None:
    """https://github.com/o/r/.../marketplace.json -> raw.githubusercontent.com base."""
    try:
        parsed = urlparse(url)
        if parsed.hostname != "github.com":
            return None
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            return None
        owner, repo = parts[0], parts[1]
        ref = "main"
        if len(parts) > 3 and parts[2] in ("blob", "tree"):
            ref = parts[3]
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}"
    except Exception:
        return None


def _catalog_entries() -> list[_MarketplaceCatalog]:
    out: list[_MarketplaceCatalog] = []
    index = catalog_dir() / "skills" / "marketplaces.yaml"
    if index.is_file():
        try:
            data = yaml.safe_load(index.read_text(encoding="utf-8"))
        except Exception:
            data = None
        rows = data.get("marketplaces") if isinstance(data, dict) else None
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict) or not row.get("id"):
                    continue
                rel = str(row.get("path") or "").strip()
                base_path = (catalog_dir() / "skills" / rel).resolve() if rel else None
                if base_path and base_path.is_file():
                    parent = base_path.parent
                else:
                    parent = catalog_dir() / "skills"
                out.append(
                    _MarketplaceCatalog(
                        id=str(row["id"]),
                        title=str(row.get("title") or row["id"]),
                        trust=str(row.get("trust") or "trusted"),
                        base_path=parent,
                        base_raw_url="",
                    )
                )
    for url in os.getenv("BUTLER_CLAUDE_MARKETPLACE_URLS", "").split(","):
        u = url.strip()
        if not u:
            continue
        raw_base = _raw_base_from_github_marketplace_url(u) or ""
        mp_id = _slug(Path(urlparse(u).path).stem or "remote")
        out.append(
            _MarketplaceCatalog(
                id=mp_id,
                title=mp_id,
                trust="community",
                base_path=None,
                base_raw_url=raw_base,
            )
        )
    return out


def _marketplace_json_for(catalog: _MarketplaceCatalog) -> dict[str, Any] | None:
    if catalog.base_path is not None:
        for name in (
            "marketplace.json",
            "marketplace-demo.json",
            ".claude-plugin/marketplace.json",
        ):
            candidate = catalog.base_path / name
            if candidate.is_file():
                return _load_marketplace_json(candidate)
    return None


def _plugins_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("plugins")
    if isinstance(raw, list):
        return [p for p in raw if isinstance(p, dict)]
    return []


def _normalize_identifier(mp_id: str, plugin_name: str) -> str:
    return f"marketplace:{mp_id}/{plugin_name}"


def _find_plugin(data: dict[str, Any], plugin_name: str) -> dict[str, Any] | None:
    want = plugin_name.strip().lower()
    for plugin in _plugins_list(data):
        name = str(plugin.get("name") or "").strip().lower()
        if name == want:
            return plugin
    return None


def _safe_rel_path(rel: str) -> str | None:
    normalized = str(rel or "").replace("\\", "/").lstrip("/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    parts = [p for p in normalized.split("/") if p and p != "."]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def _read_local_tree(base: Path, rel_dir: str) -> dict[str, str]:
    files: dict[str, str] = {}
    root = (base / rel_dir).resolve()
    if not root.is_dir():
        skill = root.parent / "SKILL.md" if root.suffix == ".md" else root / "SKILL.md"
        if skill.is_file():
            files["SKILL.md"] = skill.read_text(encoding="utf-8")
        return files
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if not path.name.lower().endswith(_ALLOWED_SUFFIXES):
            continue
        rel = path.relative_to(root).as_posix()
        try:
            files[rel] = path.read_text(encoding="utf-8")
        except OSError:
            continue
    if "SKILL.md" not in files and "skill.md" not in files:
        for alt in ("SKILL.md", "skill.md"):
            direct = root / alt
            if direct.is_file():
                files[alt] = direct.read_text(encoding="utf-8")
                break
    return files


def _fetch_raw_tree(base_raw: str, rel_dir: str) -> dict[str, str]:
    files: dict[str, str] = {}
    base = base_raw.rstrip("/")
    rel = _safe_rel_path(rel_dir) or rel_dir.strip("./")
    candidates = [
        f"{base}/{rel}/SKILL.md",
        f"{base}/{rel}/skill.md",
        f"{base}/{rel}.md",
    ]
    for url in candidates:
        if not is_safe_url(url):
            continue
        try:
            from butler.registry.url_safety import safe_registry_get

            resp = safe_registry_get(url, timeout=20.0)
            if resp.status_code == 200:
                files["SKILL.md"] = resp.text
                break
        except httpx.HTTPError:
            # Audit R2-15: network errors fall through to the next candidate.
            # ValueError from safe_registry_get's SSRF guard propagates so
            # the marketplace's caller can record it.
            continue
    for extra in ("reference.md", "README.md"):
        url = f"{base}/{rel}/{extra}"
        if is_safe_url(url):
            try:
                from butler.registry.url_safety import safe_registry_get

                resp = safe_registry_get(url, timeout=15.0)
                if resp.status_code == 200:
                    files[extra] = resp.text
            except httpx.HTTPError as exc:
                logger.debug("fetch raw tree skipped: %s", exc)
    return files


def _resolve_plugin_files(
    catalog: _MarketplaceCatalog,
    plugin: dict[str, Any],
    data: dict[str, Any],
) -> dict[str, str] | None:
    name = str(plugin.get("name") or "skill")
    source = plugin.get("source")
    rel_dirs: list[str] = []

    skills_field = plugin.get("skills")
    if isinstance(skills_field, str):
        rel_dirs.append(skills_field)
    elif isinstance(skills_field, list):
        rel_dirs.extend(str(x) for x in skills_field if x)

    commands_field = plugin.get("commands")
    if isinstance(commands_field, str):
        rel_dirs.append(commands_field)
    elif isinstance(commands_field, list):
        for cmd in commands_field:
            rel_dirs.append(str(cmd))

    if isinstance(source, str) and source.strip():
        rel_dirs.append(source)
    elif isinstance(source, dict):
        if str(source.get("source") or "").lower() == "github":
            repo = str(source.get("repo") or "").strip()
            if repo:
                gh = GitHubSource()
                subpath = str(source.get("path") or "SKILL.md").strip()
                bundle = gh.fetch(f"github:{repo}/{subpath}")
                if bundle:
                    return {k: v if isinstance(v, str) else v.decode() for k, v in bundle.files.items()}
        return None

    for rel in rel_dirs:
        safe = _safe_rel_path(rel)
        if not safe:
            continue
        if catalog.base_path is not None:
            files = _read_local_tree(catalog.base_path, safe)
            if files:
                return files
        if catalog.base_raw_url:
            files = _fetch_raw_tree(catalog.base_raw_url, safe)
            if files:
                return files

    if catalog.base_path is not None:
        mp_json = catalog.base_path / "marketplace-demo.json"
        if mp_json.is_file():
            return _read_local_tree(catalog.base_path, f"plugins/{name}")
    return None


class ClaudeMarketplaceSource(SkillSource):
    """Parse Claude Code `.claude-plugin/marketplace.json` indexes."""

    @property
    def source_id(self) -> str:
        return "marketplace"

    def _iter_hits(self, query: str, *, limit: int) -> list[SkillSearchHit]:
        q = query.strip().lower()
        hits: list[SkillSearchHit] = []
        for catalog in _catalog_entries():
            data = _marketplace_json_for(catalog)
            if not data:
                if catalog.base_raw_url and os.getenv("BUTLER_CLAUDE_MARKETPLACE_URLS"):
                    for url in os.getenv("BUTLER_CLAUDE_MARKETPLACE_URLS", "").split(","):
                        if _slug(Path(urlparse(url.strip()).path).stem or "") == catalog.id:
                            data = _fetch_marketplace_url(url.strip())
                            break
            if not data:
                continue
            for plugin in _plugins_list(data):
                name = str(plugin.get("name") or "")
                desc = str(plugin.get("description") or "")
                if q and q not in name.lower() and q not in desc.lower():
                    continue
                hits.append(
                    SkillSearchHit(
                        name=name,
                        description=desc[:500],
                        source=self.source_id,
                        identifier=_normalize_identifier(catalog.id, name),
                        trust=catalog.trust if catalog.trust != "builtin" else "trusted",
                        tags=list(plugin.get("tags") or []) if isinstance(plugin.get("tags"), list) else [],
                        extra={
                            "marketplace": catalog.id,
                            "version": plugin.get("version"),
                        },
                    )
                )
                if len(hits) >= limit:
                    return hits
        return hits

    def search(self, query: str, *, limit: int = 20) -> list[SkillSearchHit]:
        if not marketplace_enabled():
            return []
        return self._iter_hits(query, limit=limit)

    def inspect(self, identifier: str) -> SkillSearchHit | None:
        if not marketplace_enabled():
            return None
        parsed = _parse_identifier(identifier)
        if not parsed:
            return None
        mp_id, plugin_name = parsed
        for catalog in _catalog_entries():
            if catalog.id != mp_id:
                continue
            data = _marketplace_json_for(catalog)
            if not data:
                continue
            plugin = _find_plugin(data, plugin_name)
            if not plugin:
                return None
            return SkillSearchHit(
                name=str(plugin.get("name") or plugin_name),
                description=str(plugin.get("description") or ""),
                source=self.source_id,
                identifier=_normalize_identifier(mp_id, plugin_name),
                trust=catalog.trust if catalog.trust != "builtin" else "trusted",
                extra={"marketplace": mp_id, "version": plugin.get("version")},
            )
        return None

    def fetch(self, identifier: str) -> SkillBundle | None:
        if not marketplace_enabled():
            return None
        parsed = _parse_identifier(identifier)
        if not parsed:
            return None
        mp_id, plugin_name = parsed
        for catalog in _catalog_entries():
            if catalog.id != mp_id:
                continue
            data = _marketplace_json_for(catalog)
            if not data:
                continue
            plugin = _find_plugin(data, plugin_name)
            if not plugin:
                return None
            files = _resolve_plugin_files(catalog, plugin, data)
            if not files:
                return None
            skill_name = _slug(str(plugin.get("name") or plugin_name))
            return SkillBundle(
                name=skill_name,
                files=files,
                source=self.source_id,
                identifier=_normalize_identifier(mp_id, plugin_name),
                trust=catalog.trust if catalog.trust != "builtin" else "trusted",
                metadata={"marketplace": mp_id, "version": plugin.get("version")},
            )
        return None
