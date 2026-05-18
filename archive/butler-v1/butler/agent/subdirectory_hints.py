#!/usr/bin/env python3
"""Progressive subdirectory hint loading (AGENTS.md, README, etc.)."""

from __future__ import annotations

import logging
import os
import re
import shlex
from pathlib import Path
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)

_HINT_FILENAMES = ["AGENTS.md", "agents.md", "CLAUDE.md", "claude.md", ".cursorrules", "README.md"]
_MAX_HINT_CHARS = 8_000
_PATH_ARG_KEYS = {"path", "file_path", "cwd"}
_COMMAND_TOOLS = {"run_shell"}
_MAX_ANCESTOR_WALK = 5

# Heuristic token: looks like a path segment the agent might care about
_PATHLIKE_PATTERN = re.compile(r"^[./~].+|.+[/\\].+")


class SubdirectoryHintTracker:
    def __init__(self, working_dir: str | None = None):
        self.working_dir = Path(working_dir or os.getcwd()).resolve()
        self._loaded_dirs: Set[Path] = {self.working_dir}

    def check_tool_call(self, tool_name: str, tool_args: Dict[str, Any]) -> Optional[str]:
        """Check tool call for new directories and load hint files. Returns hint text or None."""
        blocks: list[str] = []

        for d in sorted(self._extract_directories(tool_name, tool_args)):
            resolved = self._directory_for_path(d)
            if resolved is None:
                continue
            cursor = resolved
            for _ in range(_MAX_ANCESTOR_WALK + 1):
                if cursor not in self._loaded_dirs:
                    hint = self._load_hints_for_directory(cursor)
                    self._loaded_dirs.add(cursor)
                    if hint:
                        blocks.append(hint)
                parent = cursor.parent
                if parent == cursor:
                    break
                cursor = parent

        if not blocks:
            return None

        text = "\n\n".join(blocks)
        if len(text) > _MAX_HINT_CHARS:
            text = text[: _MAX_HINT_CHARS] + "\n… [truncated]"
        return text

    def _extract_directories(self, tool_name: str, args: Dict[str, Any]) -> list[Path]:
        candidates: Set[Path] = set()
        for key in _PATH_ARG_KEYS:
            if key in args and args[key]:
                self._add_path_candidate(str(args[key]), candidates)

        if tool_name in _COMMAND_TOOLS:
            cmd = args.get("command")
            if isinstance(cmd, str):
                self._extract_paths_from_command(cmd, candidates)

        return list(candidates)

    def _add_path_candidate(self, raw_path: str, candidates: Set[Path]) -> None:
        raw_path = raw_path.strip()
        if not raw_path or raw_path.startswith("-"):
            return
        try:
            p = Path(raw_path).expanduser()
            if not p.is_absolute():
                p = (self.working_dir / p).resolve()
            else:
                p = p.resolve()
        except OSError:
            return
        candidates.add(p)

    def _extract_paths_from_command(self, cmd: str, candidates: Set[Path]) -> None:
        try:
            tokens = shlex.split(cmd)
        except ValueError:
            tokens = cmd.split()

        for tok in tokens:
            if len(tok) < 2:
                continue
            if tok.startswith(("http://", "https://", "git@", "ssh://")):
                continue
            if _PATHLIKE_PATTERN.match(tok) or tok in (".", ".."):
                self._add_path_candidate(tok, candidates)

    def _directory_for_path(self, p: Path) -> Optional[Path]:
        try:
            if p.is_file():
                return p.parent
            if p.is_dir():
                return p
        except OSError:
            return None
        # Path may not exist yet; treat as file if it has a suffix resembling a file
        if p.suffix and p.suffix not in {".", ""}:
            return p.parent
        return p

    def _load_hints_for_directory(self, directory: Path) -> Optional[str]:
        try:
            if not directory.is_dir():
                return None
        except OSError:
            return None

        for name in _HINT_FILENAMES:
            fp = directory / name
            try:
                if not fp.is_file():
                    continue
            except OSError:
                continue
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                logger.debug("Could not read hint file %s: %s", fp, e)
                return None

            try:
                rel = str(fp.parent.relative_to(self.working_dir))
            except ValueError:
                rel = str(fp.parent)
            header = f"[Subdirectory context discovered: {rel}]\n"
            body = content
            max_body = max(0, _MAX_HINT_CHARS - len(header) - 200)
            if len(body) > max_body:
                body = body[:max_body] + "\n… [truncated]"
            return header + body

        return None
