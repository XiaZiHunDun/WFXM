"""Multi-strategy code search — rg + glob + ctags + regex.

Formal model from v4-dev-engine-theory.md §2.4:
  Locate(intent) → [(file, range, relevance)] via:
    - Regex search (rg)
    - File structure exploration (glob + directory)
    - Symbol navigation (ctags with regex fallback; DE-GAP-3)
    - Semantic search (future: embeddings)
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from butler.dev_engine.dev_state import SearchHit

MAX_SEARCH_RESULTS = 50
SEARCH_TIMEOUT = 15


def search_text(
    pattern: str,
    workspace: Path,
    *,
    glob_filter: str = "",
    max_results: int = MAX_SEARCH_RESULTS,
) -> list[SearchHit]:
    """Regex text search using ripgrep (rg) or fallback.

    Strategy layer 2: textual search.
    """
    from butler.dev_engine.code_search_ops import rg_text_search_hits

    hits: list[SearchHit] = []
    try:
        hits = rg_text_search_hits(
            pattern,
            workspace,
            glob_filter=glob_filter,
            max_results=max_results,
            timeout=SEARCH_TIMEOUT,
        )
    except FileNotFoundError:
        hits = _fallback_grep(pattern, workspace, max_results)

    return hits


def search_files(
    pattern: str,
    workspace: Path,
    *,
    max_results: int = MAX_SEARCH_RESULTS,
) -> list[SearchHit]:
    """File name / glob search.

    Strategy layer 1: structural search.
    """
    from butler.dev_engine.code_search_ops import walk_file_search_hits

    return walk_file_search_hits(
        pattern,
        workspace,
        should_skip_dir=_should_skip_dir,
        max_results=max_results,
    )


def search_symbols(
    name: str,
    workspace: Path,
    *,
    max_results: int = MAX_SEARCH_RESULTS,
) -> list[SearchHit]:
    """Symbol search — function/class/variable definitions (DE-GAP-3).

    Strategy layer 3: symbolic search.
    Tries ctags first (fast, language-aware), then falls back to regex patterns.
    """
    hits = _ctags_search(name, workspace, max_results=max_results)
    if hits:
        return hits
    return _regex_symbol_search(name, workspace, max_results=max_results)


def _regex_symbol_search(
    name: str,
    workspace: Path,
    *,
    max_results: int = MAX_SEARCH_RESULTS,
) -> list[SearchHit]:
    """Regex-based symbol search — fallback when ctags is unavailable."""
    patterns = [
        rf"(?:def|async\s+def)\s+{re.escape(name)}\s*\(",
        rf"class\s+{re.escape(name)}[\s(:]",
        rf"(?:const|let|var|function)\s+{re.escape(name)}\b",
        rf"{re.escape(name)}\s*=\s*",
    ]
    combined = "|".join(f"({p})" for p in patterns)
    return search_text(combined, workspace, max_results=max_results)


def _ctags_search(
    name: str,
    workspace: Path,
    *,
    max_results: int = MAX_SEARCH_RESULTS,
) -> list[SearchHit]:
    """Use Universal Ctags for language-aware symbol extraction.

    Returns empty list if ctags is not installed or fails.
    """
    try:
        result = subprocess.run(
            [
                "ctags",
                "--output-format=json",
                "--sort=no",
                "-R",
                "--fields=+n",
                "--kinds-all=*",
                str(workspace),
            ],
            capture_output=True,
            text=True,
            timeout=SEARCH_TIMEOUT,
            cwd=str(workspace),
        )
        if result.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []

    import json as _json

    hits: list[SearchHit] = []
    name_lower = name.lower()
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            tag = _json.loads(line)
        except (ValueError, _json.JSONDecodeError):
            continue
        tag_name = str(tag.get("name", ""))
        if tag_name.lower() != name_lower and name_lower not in tag_name.lower():
            continue
        file_path = str(tag.get("path", ""))
        if not file_path:
            continue
        try:
            rel = os.path.relpath(file_path, workspace)
        except ValueError:
            rel = file_path
        line_num = int(tag.get("line", 0))
        kind = str(tag.get("kind", ""))
        scope_name = str(tag.get("scope", "") or tag.get("scopeKind", "") or "")
        snippet = f"{kind}: {tag_name}"
        if scope_name:
            snippet += f" (in {scope_name})"

        relevance = 1.0 if tag_name.lower() == name_lower else 0.8
        hits.append(SearchHit(
            path=rel,
            range_start=line_num,
            range_end=line_num,
            relevance=relevance,
            snippet=snippet,
        ))
        if len(hits) >= max_results:
            break

    return hits


def _should_skip_dir(path: str) -> bool:
    skip_dirs = {
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        ".mypy_cache", ".pytest_cache", ".tox", "dist", "build",
        ".eggs", "*.egg-info",
    }
    basename = os.path.basename(path)
    return basename in skip_dirs or basename.startswith(".")


def _fallback_grep(
    pattern: str,
    workspace: Path,
    max_results: int,
) -> list[SearchHit]:
    """Pure-Python fallback when rg is not available."""
    hits: list[SearchHit] = []
    try:
        compiled = re.compile(pattern)
    except re.error:
        return hits

    for root, _dirs, files in os.walk(workspace):
        if _should_skip_dir(root):
            continue
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if compiled.search(line):
                            rel = os.path.relpath(fpath, workspace)
                            hits.append(SearchHit(
                                path=rel,
                                range_start=i,
                                range_end=i,
                                relevance=0.9,
                                snippet=line.strip()[:200],
                            ))
                            if len(hits) >= max_results:
                                return hits
                            break
            except (OSError, UnicodeDecodeError):
                continue
    return hits
