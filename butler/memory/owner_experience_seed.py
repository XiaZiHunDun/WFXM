"""Purge benchmark filler and idempotently seed owner experience pointers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from butler.memory.butler_memory import ButlerMemory
from butler.memory.semantic_index import SOURCE_EXPERIENCE

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SEED_PATH = _REPO_ROOT / "data" / "seed_owner_experiences.json"
_SEED_MARKER = "seed:owner-experience"


def _seed_tag(seed_id: str) -> str:
    return f"seed:id:{seed_id}"


def purge_benchmark_filler(
    butler_home: Path,
    *,
    tenant_id: str = "default",
) -> dict[str, Any]:
    """Remove MB5 capacity-benchmark rows and sync vector deletions."""
    bm = ButlerMemory(Path(butler_home).expanduser().resolve(), tenant_id=tenant_id)
    deleted_ids = bm.experience.purge_benchmark_capacity_entries()
    vector_deleted = 0
    sem = bm.semantic
    if sem is not None:
        for row_id in deleted_ids:
            try:
                sem.delete(SOURCE_EXPERIENCE, str(row_id))
                vector_deleted += 1
            except Exception as exc:
                logger.debug("Vector delete skipped for experience %s: %s", row_id, exc)
    try:
        bm.close()
    except Exception:
        pass
    return {
        "deleted_sql_rows": len(deleted_ids),
        "deleted_vector_rows": vector_deleted,
        "deleted_ids": deleted_ids[:20],
    }


def seed_owner_experiences(
    butler_home: Path,
    *,
    tenant_id: str = "default",
    seed_path: Path | None = None,
) -> dict[str, Any]:
    """Load ``data/seed_owner_experiences.json``; skip rows already present."""
    path = Path(seed_path or _DEFAULT_SEED_PATH).resolve()
    if not path.is_file():
        return {"ok": False, "error": f"seed file not found: {path}", "added": 0, "skipped": 0}

    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "error": str(exc), "added": 0, "skipped": 0}

    if not isinstance(records, list):
        return {"ok": False, "error": "seed file must be a JSON array", "added": 0, "skipped": 0}

    bm = ButlerMemory(Path(butler_home).expanduser().resolve(), tenant_id=tenant_id)
    added = 0
    skipped = 0
    errors: list[str] = []

    for rec in records:
        if not isinstance(rec, dict):
            continue
        seed_id = str(rec.get("seed_id") or "").strip()
        content = str(rec.get("content") or "").strip()
        if not seed_id or not content:
            continue
        if bm.experience.has_tag_substring(_seed_tag(seed_id)):
            skipped += 1
            continue

        tags = rec.get("tags") or []
        if isinstance(tags, str):
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        elif isinstance(tags, list):
            tag_list = [str(t).strip() for t in tags if str(t).strip()]
        else:
            tag_list = []
        if _SEED_MARKER not in tag_list:
            tag_list.insert(0, _SEED_MARKER)
        if _seed_tag(seed_id) not in tag_list:
            tag_list.append(_seed_tag(seed_id))

        row_id = bm.add_experience(
            str(rec.get("project") or ""),
            str(rec.get("category") or "note"),
            content,
            tags=tag_list,
        )
        if row_id > 0:
            added += 1
        else:
            errors.append(seed_id)

    try:
        bm.close()
    except Exception:
        pass

    return {
        "ok": len(errors) == 0,
        "added": added,
        "skipped": skipped,
        "errors": errors,
        "seed_path": str(path),
    }


def run_owner_experience_seed(
    butler_home: Path,
    *,
    tenant_id: str = "default",
    seed_path: Path | None = None,
    purge_filler: bool = True,
) -> dict[str, Any]:
    """P0 pipeline: optional filler purge then idempotent owner seed."""
    out: dict[str, Any] = {"ok": True, "tenant_id": tenant_id}
    if purge_filler:
        out["purge"] = purge_benchmark_filler(butler_home, tenant_id=tenant_id)
    out["seed"] = seed_owner_experiences(
        butler_home, tenant_id=tenant_id, seed_path=seed_path
    )
    out["ok"] = bool(out["seed"].get("ok"))
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    from butler.config import get_butler_home

    p = argparse.ArgumentParser(description="Purge MB5 filler and seed owner experience pointers")
    p.add_argument("--tenant", default="default")
    p.add_argument("--seed-path", default="")
    p.add_argument("--no-purge", action="store_true")
    args = p.parse_args(argv)
    seed_path = Path(args.seed_path).expanduser() if args.seed_path else None
    result = run_owner_experience_seed(
        get_butler_home(),
        tenant_id=str(args.tenant),
        seed_path=seed_path,
        purge_filler=not args.no_purge,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "main",
    "purge_benchmark_filler",
    "run_owner_experience_seed",
    "seed_owner_experiences",
]
