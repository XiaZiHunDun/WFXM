"""Code search subprocess / walk best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from butler.dev_engine.dev_state import SearchHit

logger = logging.getLogger(__name__)


def rg_text_search_hits(
    pattern: str,
    workspace: Path,
    *,
    glob_filter: str = "",
    max_results: int = 50,
    timeout: int = 15,
) -> list[SearchHit]:
    hits: list[SearchHit] = []
    try:
        cmd = ["rg", "--line-number", "--no-heading", "--max-count", "5"]
        if glob_filter:
            cmd.extend(["--glob", glob_filter])
        cmd.extend(["--max-filesize", "1M", pattern, str(workspace)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workspace),
        )
        for line in result.stdout.splitlines()[:max_results]:
            parts = line.split(":", 2)
            if len(parts) >= 3:
                file_path = parts[0]
                try:
                    line_num = int(parts[1])
                except ValueError:
                    continue
                snippet = parts[2].strip()[:200]
                hits.append(SearchHit(
                    path=file_path,
                    range_start=line_num,
                    range_end=line_num,
                    relevance=1.0,
                    snippet=snippet,
                ))
    except FileNotFoundError:
        raise
    except subprocess.TimeoutExpired:
        logger.warning("rg search timed out after %ds", timeout)
    except Exception as exc:
        logger.warning("Search error: %s", exc)
    return hits


def walk_file_search_hits(
    pattern: str,
    workspace: Path,
    *,
    should_skip_dir: Callable[[str], bool],
    max_results: int = 50,
) -> list[SearchHit]:
    import fnmatch

    hits: list[SearchHit] = []
    try:
        for root, _dirs, files in os.walk(workspace):
            if should_skip_dir(root):
                continue
            for fname in files:
                if fnmatch.fnmatch(fname, pattern) or pattern.lower() in fname.lower():
                    rel_path = os.path.relpath(os.path.join(root, fname), workspace)
                    hits.append(SearchHit(
                        path=rel_path,
                        relevance=1.0 if fnmatch.fnmatch(fname, pattern) else 0.8,
                    ))
                    if len(hits) >= max_results:
                        return hits
    except Exception as exc:
        logger.warning("File search error: %s", exc)
    return hits
