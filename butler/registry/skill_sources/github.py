"""Fetch skills from GitHub via Contents API or raw URL."""

from __future__ import annotations

import base64
import logging
import os
import re
from typing import Any

import httpx

from butler.registry.skill_sources.base import SkillSource
from butler.registry.skill_types import SkillBundle, SkillSearchHit

logger = logging.getLogger(__name__)

_GH_API = "https://api.github.com"
_RAW = "https://raw.githubusercontent.com"


def _auth_headers() -> dict[str, str]:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    return {"Accept": "application/vnd.github+json"}


def _parse_identifier(identifier: str) -> tuple[str, str, str] | None:
    """github:owner/repo/path/to/SKILL.md or owner/repo/path"""
    ident = identifier.strip()
    if ident.startswith("github:"):
        ident = ident[7:]
    parts = ident.split("/")
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    path = "/".join(parts[2:]) if len(parts) > 2 else "SKILL.md"
    if not path.lower().endswith(".md"):
        path = f"{path.rstrip('/')}/SKILL.md"
    return owner, repo, path


class GitHubSource(SkillSource):
    @property
    def source_id(self) -> str:
        return "github"

    def search(self, query: str, *, limit: int = 20) -> list[SkillSearchHit]:
        q = query.strip().lower()
        if "/" not in q:
            return []
        parts = q.split("/")
        if len(parts) < 2:
            return []
        owner, repo = parts[0], parts[1]
        ident = f"github:{owner}/{repo}"
        if len(parts) > 2:
            ident = f"github:{owner}/{repo}/{'/'.join(parts[2:])}"
        return [
            SkillSearchHit(
                name=parts[-1].replace(".md", "") or repo,
                description=f"GitHub {owner}/{repo}",
                source=self.source_id,
                identifier=ident,
                trust=_trust_for_repo(owner, repo),
                extra={"repo": f"{owner}/{repo}"},
            )
        ][:limit]

    def inspect(self, identifier: str) -> SkillSearchHit | None:
        parsed = _parse_identifier(identifier)
        if not parsed:
            return None
        owner, repo, path = parsed
        ident = f"github:{owner}/{repo}/{path}"
        return SkillSearchHit(
            name=path.split("/")[-1].replace(".md", "") or repo,
            description=f"GitHub {owner}/{repo}/{path}",
            source=self.source_id,
            identifier=ident,
            trust=_trust_for_repo(owner, repo),
            extra={"repo": f"{owner}/{repo}", "path": path},
        )

    def fetch(self, identifier: str) -> SkillBundle | None:
        parsed = _parse_identifier(identifier)
        if not parsed:
            return None
        owner, repo, path = parsed
        text = _fetch_raw(owner, repo, path) or _fetch_api(owner, repo, path)
        if not text:
            return None
        name = _name_from_frontmatter(text) or path.split("/")[-1].replace(".md", "") or repo
        name = re.sub(r"[^a-z0-9._-]+", "-", name.lower())[:64]
        return SkillBundle(
            name=name,
            files={"SKILL.md": text},
            source=self.source_id,
            identifier=f"github:{owner}/{repo}/{path}",
            trust=_trust_for_repo(owner, repo),
            metadata={"repo": f"{owner}/{repo}", "path": path},
        )


def _trust_for_repo(owner: str, repo: str) -> str:
    trusted = os.getenv("BUTLER_SKILL_TRUSTED_REPOS", "").strip()
    key = f"{owner}/{repo}".lower()
    for part in trusted.split(","):
        if part.strip().lower() == key:
            return "trusted"
    return "community"


def _fetch_raw(owner: str, repo: str, path: str, ref: str = "main") -> str | None:
    for branch in (ref, "master"):
        url = f"{_RAW}/{owner}/{repo}/{branch}/{path}"
        try:
            from butler.registry.url_safety import safe_registry_get

            resp = safe_registry_get(url)
            if resp.status_code == 200:
                return resp.text
        except Exception:
            continue
    return None


def _fetch_api(owner: str, repo: str, path: str) -> str | None:
    url = f"{_GH_API}/repos/{owner}/{repo}/contents/{path}"
    try:
        resp = httpx.get(url, headers=_auth_headers(), timeout=25.0)
        if resp.status_code != 200:
            return None
        data: Any = resp.json()
        if not isinstance(data, dict):
            return None
        enc = data.get("content")
        if not enc:
            return None
        raw = base64.b64decode(enc)
        return raw.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.debug("github api fetch failed: %s", exc)
        return None


def _name_from_frontmatter(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    block = text[4:end]
    for line in block.splitlines():
        if line.strip().lower().startswith("name:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return None
