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

# Audit R2-15: surface SSRF rejections instead of swallowing them as generic
# "fetch failed". The inner loop used ``except Exception: continue`` which
# hid the ValueError raised by ``safe_registry_get`` for unsafe URLs. We
# now narrow the inner loop to network errors only, let SSRF rejection
# propagate, and catch it at the ``fetch()`` boundary where the URL is
# recorded for /诊断 to aggregate. Same shape as R2-9/11/12/13/14
# diagnostics buffers.
_MAX_SSRF_REJECTION_ENTRIES = 50
_ssrf_rejections: list[dict[str, Any]] = []


def recent_ssrf_rejections() -> list[dict[str, Any]]:
    """Read the SSRF-rejection diagnostics buffer (test + /诊断 interface)."""
    return list(_ssrf_rejections)


def reset_ssrf_rejections() -> None:
    """Clear the SSRF-rejection diagnostics buffer (test helper)."""
    _ssrf_rejections.clear()


def _record_ssrf_rejection(source: str, url: str, reason: str) -> None:
    """Append an SSRF rejection event and cap the buffer to its max length."""
    _ssrf_rejections.append({"source": source, "url": url, "reason": reason})
    if len(_ssrf_rejections) > _MAX_SSRF_REJECTION_ENTRIES:
        del _ssrf_rejections[: len(_ssrf_rejections) - _MAX_SSRF_REJECTION_ENTRIES]


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
        try:
            text = _fetch_raw(owner, repo, path) or _fetch_api(owner, repo, path)
        except ValueError as exc:
            # Audit R2-15: ``safe_registry_get`` rejected the URL as unsafe.
            # This is a security signal, not a generic "fetch failed" — log
            # at WARNING with the URL, record the event for /诊断, and
            # return None so the caller's user-facing flow is not disrupted.
            url = f"github:{owner}/{repo}/{path}"
            logger.warning(
                "github fetch blocked by SSRF guard for %s: %s", url, exc
            )
            _record_ssrf_rejection(self.source_id, url, str(exc))
            return None
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
        except httpx.HTTPError:
            # Audit R2-15: network / timeout / 5xx fall through to the next
            # branch. ValueError from safe_registry_get's SSRF guard is
            # deliberately NOT caught here so it propagates to the fetch()
            # boundary for /诊断 recording.
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
    except httpx.HTTPError as exc:
        # Audit R2-15: narrow except — only network errors fall through.
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


_TREE_SUFFIXES = (".md", ".txt", ".json", ".yaml", ".yml")
_MAX_TREE_FILES = 120
_MAX_TREE_BYTES = 2 * 1024 * 1024


def _github_dir_path(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").strip("/")
    low = normalized.lower()
    if low.endswith("/skill.md") or low.endswith("/skills.md"):
        return normalized.rsplit("/", 1)[0]
    if low.endswith(".md"):
        return normalized.rsplit("/", 1)[0]
    return normalized


def fetch_github_directory(
    owner: str,
    repo: str,
    dir_path: str,
    *,
    ref: str = "",
) -> dict[str, str] | None:
    """Recursively fetch text files under a GitHub directory via Contents API."""
    root = _github_dir_path(dir_path)
    if not root:
        return None
    refs = [ref.strip()] if ref.strip() else []
    refs.extend(b for b in ("master", "main") if b not in refs)
    for branch in refs:
        files = _fetch_contents_tree(owner, repo, root, ref=branch, require_skill_md=False)
        if files and ("SKILL.md" in files or "skill.md" in files):
            return files
    return None


def _fetch_contents_tree(
    owner: str,
    repo: str,
    path: str,
    *,
    ref: str,
    require_skill_md: bool = True,
) -> dict[str, str] | None:
    url = f"{_GH_API}/repos/{owner}/{repo}/contents/{path}"
    params = {"ref": ref} if ref else None
    try:
        resp = httpx.get(url, headers=_auth_headers(), params=params, timeout=25.0)
    except httpx.HTTPError as exc:
        logger.debug("github contents tree %s: %s", path, exc)
        return None
    if resp.status_code != 200:
        return None
    data = resp.json()
    if not isinstance(data, list):
        return None
    out: dict[str, str] = {}
    total = 0
    pending_dirs: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        item_path = str(item.get("path") or "")
        if item.get("type") == "dir":
            pending_dirs.append(item_path)
            continue
        if item.get("type") != "file":
            continue
        if not name.lower().endswith(_TREE_SUFFIXES):
            continue
        rel = item_path
        if rel.startswith(f"{path}/"):
            rel = rel[len(path) + 1 :]
        elif rel == path:
            rel = name
        text = _download_github_file(item)
        if text is None:
            continue
        piece = text.encode("utf-8")
        total += len(piece)
        if total > _MAX_TREE_BYTES or len(out) >= _MAX_TREE_FILES:
            break
        out[rel] = text
    for sub in pending_dirs:
        if len(out) >= _MAX_TREE_FILES or total >= _MAX_TREE_BYTES:
            break
        sub_files = _fetch_contents_tree(
            owner, repo, sub, ref=ref, require_skill_md=False
        )
        if not sub_files:
            continue
        prefix = sub
        if prefix.startswith(f"{path}/"):
            prefix = prefix[len(path) + 1 :]
        for rel, text in sub_files.items():
            key = f"{prefix}/{rel}" if prefix else rel
            piece = text.encode("utf-8")
            if total + len(piece) > _MAX_TREE_BYTES or len(out) >= _MAX_TREE_FILES:
                break
            total += len(piece)
            out[key] = text
    if require_skill_md and "SKILL.md" not in out and "skill.md" not in out:
        return None
    return out or None


def _download_github_file(item: dict[str, Any]) -> str | None:
    download = str(item.get("download_url") or "").strip()
    if download:
        try:
            from butler.registry.url_safety import safe_registry_get

            resp = safe_registry_get(download, timeout=20.0)
            if resp.status_code == 200:
                return resp.text
        except httpx.HTTPError as exc:
            logger.debug("github download_url failed: %s", exc)
        except ValueError:
            raise
    enc = item.get("content")
    if not enc:
        return None
    try:
        raw = base64.b64decode(enc)
        return raw.decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return None
