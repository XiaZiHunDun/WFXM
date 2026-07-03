"""Parse ``.butlerignore`` patterns (Cursor ``.cursorignore`` subset)."""

from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_IGNORE_FILENAMES = (".butlerignore",)
_PROTECTED_WRITE_GLOBS = (
    ".butler/*.json",
    ".butler/**/*.json",
    ".git/config",
    ".git/hooks/**",
    ".git/info/attributes",
    ".env",
    ".env.*",
)


def _ignore_file_candidates(workspace: Path) -> list[Path]:
    ws = workspace.resolve(strict=False)
    return [ws / name for name in _IGNORE_FILENAMES] + [ws / ".butler" / ".butlerignore"]


def load_ignore_patterns(workspace: Path | None = None) -> tuple[str, ...]:
    """Return normalized glob patterns from workspace ignore files."""
    from butler.tools.butlerignore_ops import current_workspace_root_safe

    if workspace is None:
        workspace = current_workspace_root_safe()
    if workspace is None:
        return ()

    patterns: list[str] = []
    for path in _ignore_file_candidates(workspace):
        if not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                if raw.startswith("!"):
                    continue
                patterns.append(raw.replace("\\", "/"))
        except OSError as exc:
            logger.debug("butlerignore read skipped %s: %s", path, exc)
    return tuple(patterns)


def _rel_posix(path: Path, workspace: Path) -> str | None:
    try:
        rel = path.resolve(strict=False).relative_to(workspace.resolve(strict=False))
    except ValueError:
        return None
    return rel.as_posix()


def matches_ignore_pattern(rel_posix: str, pattern: str) -> bool:
    pat = pattern.strip().replace("\\", "/")
    if not pat:
        return False
    if pat.endswith("/"):
        pat = pat.rstrip("/") + "/**"
    if "**" in pat:
        return fnmatch.fnmatch(rel_posix, pat) or fnmatch.fnmatch(
            rel_posix, pat.replace("**", "*")
        )
    if "/" not in pat:
        base = rel_posix.split("/")[-1]
        return fnmatch.fnmatch(base, pat) or fnmatch.fnmatch(rel_posix, pat)
    return fnmatch.fnmatch(rel_posix, pat)


def is_butlerignored(path: Path, *, workspace: Path | None = None) -> bool:
    """True when ``path`` matches ``.butlerignore`` under ``workspace``."""
    from butler.tools.butlerignore_ops import current_workspace_root_safe

    if workspace is None:
        workspace = current_workspace_root_safe()
    if workspace is None:
        return False
    rel = _rel_posix(path, workspace)
    if rel is None:
        return False
    for pattern in load_ignore_patterns(workspace):
        if matches_ignore_pattern(rel, pattern):
            return True
    return False


def is_protected_write_path(path: Path, *, workspace: Path | None = None) -> bool:
    """Hard-coded write-protected paths (Cursor sandbox protected paths subset)."""
    from butler.tools.butlerignore_ops import current_workspace_root_safe

    if workspace is None:
        workspace = current_workspace_root_safe()
    if workspace is None:
        return False
    rel = _rel_posix(path, workspace)
    if rel is None:
        return False
    for pattern in _PROTECTED_WRITE_GLOBS:
        if matches_ignore_pattern(rel, pattern):
            return True
    return is_butlerignored(path, workspace=workspace)


def credential_mask_paths() -> list[str]:
    """Host credential paths masked inside OS sandbox (tmpfs overlay)."""
    home = Path.home()
    candidates = [
        home / ".ssh",
        home / ".aws" / "credentials",
        home / ".config" / "gcloud",
        home / ".docker" / "config.json",
    ]
    env_path = os.getenv("BUTLER_SECRETS_PATH", "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())
    out: list[str] = []
    for path in candidates:
        try:
            resolved = str(path.expanduser().resolve(strict=False))
        except OSError:
            continue
        if Path(resolved).exists() and resolved not in out:
            out.append(resolved)
    return out


__all__ = [
    "credential_mask_paths",
    "is_butlerignored",
    "is_protected_write_path",
    "load_ignore_patterns",
    "matches_ignore_pattern",
]
