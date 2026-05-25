"""Canonicalize shell commands for stable approval fingerprints (Codex subset)."""

from __future__ import annotations

import re
import shlex
from typing import Sequence

_BASH_NAMES = frozenset({"bash", "sh", "zsh", "/bin/bash", "/bin/sh", "/usr/bin/bash"})
_LC_FLAGS = frozenset({"-lc", "-c", "/c"})


def _split_command(command: str) -> list[str]:
    text = (command or "").strip()
    if not text:
        return []
    try:
        return shlex.split(text, posix=True)
    except ValueError:
        return text.split()


def canonicalize_command_for_approval(command: str) -> str:
    """
    Normalize wrapper paths so `/bin/bash -lc 'git status'` and `bash -lc git status`
    share the same approval fingerprint string.
    """
    argv = _split_command(command)
    if not argv:
        return ""

    prog = argv[0].lower()
    base = prog.rsplit("/", 1)[-1]
    if base in _BASH_NAMES and len(argv) >= 2:
        flag = argv[1]
        if flag in _LC_FLAGS and len(argv) >= 3:
            script = " ".join(argv[2:])
            mode = flag
            return f"__butler_shell__:{mode}:{_normalize_script(script)}"
        if flag in _LC_FLAGS and len(argv) == 2:
            return f"__butler_shell__:{flag}:"

    return " ".join(_normalize_token(t) for t in argv)


def _normalize_token(token: str) -> str:
    t = token.strip()
    if t.startswith("/") and "/" in t[1:]:
        return t.rsplit("/", 1)[-1]
    return t


def _normalize_script(script: str) -> str:
    body = script.strip()
    if (body.startswith("'") and body.endswith("'")) or (
        body.startswith('"') and body.endswith('"')
    ):
        body = body[1:-1].strip()
    body = re.sub(r"\s+", " ", body)
    return body


def canonical_argv_list(argv: Sequence[str]) -> str:
    if not argv:
        return ""
    return canonicalize_command_for_approval(" ".join(shlex.quote(str(a)) for a in argv))


__all__ = ["canonical_argv_list", "canonicalize_command_for_approval"]
