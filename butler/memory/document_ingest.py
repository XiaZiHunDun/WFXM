"""EXT-3: opt-in document ingest → ``.butler/ingest/*.md`` for semantic reindex."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_INGEST_SUFFIXES = frozenset(
    {".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".xls", ".html", ".htm"}
)
_MANIFEST = "manifest.json"


def ingest_enabled() -> bool:
    return env_truthy("BUTLER_INGEST_ENABLED", default=False)


def ingest_output_root(workspace: Path) -> Path:
    return Path(workspace).expanduser().resolve() / ".butler" / "ingest"


def _load_stack(workspace: Path) -> dict[str, Any] | None:
    stack = workspace / "stack.yaml"
    if not stack.is_file():
        return None
    try:
        data = yaml.safe_load(stack.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, yaml.YAMLError) as exc:
        logger.debug("stack load failed %s: %s", stack, exc)
        return None


def pilot_dirs_from_stack(workspace: Path) -> list[Path]:
    data = _load_stack(workspace)
    if not data:
        return []
    raw = data.get("ingest_pilot_dirs")
    if not isinstance(raw, list):
        return []
    ws = workspace.resolve()
    out: list[Path] = []
    for item in raw:
        rel = str(item).strip().replace("\\", "/").lstrip("/")
        if not rel or ".." in rel.split("/"):
            continue
        path = (ws / rel).resolve()
        try:
            path.relative_to(ws)
        except ValueError:
            continue
        if path.is_dir():
            out.append(path)
    return out


def _safe_output_path(workspace: Path, src: Path, pilot_root: Path) -> Path | None:
    ws = workspace.resolve()
    try:
        rel = src.resolve().relative_to(pilot_root.resolve())
    except ValueError:
        return None
    try:
        pilot_root.resolve().relative_to(ws)
    except ValueError:
        return None
    rel_posix = rel.as_posix()
    if ".." in rel_posix.split("/"):
        return None
    stem = Path(rel_posix).with_suffix(".md").as_posix()
    out = ingest_output_root(ws) / stem
    try:
        out.resolve().relative_to(ingest_output_root(ws).resolve())
    except ValueError:
        return None
    return out


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _convert_to_markdown(path: Path) -> str:
    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise RuntimeError(
            '缺少 markitdown：pip install -e ".[documents]"'
        ) from exc
    result = MarkItDown().convert(str(path))
    text = str(getattr(result, "text_content", None) or "").strip()
    if not text:
        raise RuntimeError(f"转换结果为空: {path}")
    return text


@dataclass(frozen=True)
class IngestFileResult:
    source: str
    output: str
    status: str  # written | skipped | failed
    detail: str = ""


def ingest_file(
    workspace: Path,
    src: Path,
    *,
    pilot_root: Path,
    dry_run: bool = False,
    force: bool = False,
) -> IngestFileResult:
    src_p = src.resolve()
    out = _safe_output_path(workspace, src_p, pilot_root)
    if out is None:
        return IngestFileResult(str(src_p), "", "failed", "路径越界")
    if not dry_run and not force and out.is_file():
        manifest = _read_manifest(workspace)
        key = out.relative_to(ingest_output_root(workspace)).as_posix()
        prev = manifest.get("files", {}).get(key, {})
        if prev.get("source_hash") == _file_hash(src_p):
            return IngestFileResult(str(src_p), str(out), "skipped", "未变更")
    if dry_run:
        return IngestFileResult(str(src_p), str(out), "written", "[dry-run]")
    from butler.memory.document_ingest_ops import convert_document_to_markdown_safe

    text, convert_err = convert_document_to_markdown_safe(_convert_to_markdown, src_p)
    if convert_err is not None:
        return IngestFileResult(str(src_p), str(out), "failed", convert_err)
    header = (
        f"---\n"
        f"ingest_source: {src_p.name}\n"
        f"ingest_path: {src_p}\n"
        f"ingested_at: {datetime.now(timezone.utc).isoformat()}\n"
        f"---\n\n"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + text, encoding="utf-8")
    return IngestFileResult(str(src_p), str(out), "written", f"{len(text)} chars")


def ingest_workspace(
    workspace: Path | str,
    *,
    dirs: list[Path] | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    if not ingest_enabled() and not dry_run:
        return {
            "ok": False,
            "error": "BUTLER_INGEST_ENABLED=0（设为 1 后重试）",
            "results": [],
        }
    ws = Path(workspace).expanduser().resolve()
    scan_roots = dirs if dirs is not None else pilot_dirs_from_stack(ws)
    if not scan_roots:
        return {
            "ok": False,
            "error": "无 ingest 目录（stack.yaml ingest_pilot_dirs 或 --dir）",
            "results": [],
        }
    results: list[IngestFileResult] = []
    for root in scan_roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in _INGEST_SUFFIXES:
                continue
            results.append(ingest_file(ws, path, pilot_root=root, dry_run=dry_run, force=force))
    written = [r for r in results if r.status == "written"]
    failed = [r for r in results if r.status == "failed"]
    if not dry_run and written:
        _update_manifest(ws, results)
    return {
        "ok": not failed,
        "workspace": str(ws),
        "scanned_dirs": [str(p) for p in scan_roots],
        "written": len(written),
        "skipped": sum(1 for r in results if r.status == "skipped"),
        "failed": len(failed),
        "results": [r.__dict__ for r in results],
    }


def _read_manifest(workspace: Path) -> dict[str, Any]:
    path = ingest_output_root(workspace) / _MANIFEST
    if not path.is_file():
        return {"version": 1, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"version": 1, "files": {}}
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "files": {}}


def _update_manifest(workspace: Path, results: list[IngestFileResult]) -> None:
    root = ingest_output_root(workspace)
    root.mkdir(parents=True, exist_ok=True)
    manifest = _read_manifest(workspace)
    files = manifest.setdefault("files", {})
    if not isinstance(files, dict):
        files = {}
        manifest["files"] = files
    for row in results:
        if row.status != "written" or not row.output:
            continue
        out = Path(row.output)
        if not out.is_file():
            continue
        key = out.relative_to(root).as_posix()
        src = Path(row.source)
        files[key] = {
            "source": row.source,
            "source_hash": _file_hash(src) if src.is_file() else "",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    (root / _MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def ingest_stats(workspace: Path) -> dict[str, Any]:
    root = ingest_output_root(workspace)
    if not root.is_dir():
        return {"md_files": 0, "enabled": ingest_enabled()}
    md_files = sum(1 for p in root.rglob("*.md") if p.is_file())
    manifest = _read_manifest(workspace)
    return {
        "enabled": ingest_enabled(),
        "md_files": md_files,
        "manifest_entries": len(manifest.get("files") or {}),
        "path": str(root),
    }


__all__ = [
    "ingest_enabled",
    "ingest_file",
    "ingest_output_root",
    "ingest_stats",
    "ingest_workspace",
    "pilot_dirs_from_stack",
]
