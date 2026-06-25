"""Observation store lines for ``/诊断 详细`` and ``butler memory observations``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.memory.observation_migrate import observations_tsv_path
from butler.memory.observation_store import ObservationStore, observations_db_path
from butler.memory_settings import resolve_memory_config
import logging


logger = logging.getLogger(__name__)


def collect_observation_store_stats(workspace: Path | None) -> dict[str, Any]:
    if workspace is None:
        return {"ok": False, "reason": "no_workspace"}
    ws = Path(workspace).expanduser().resolve()
    db_path = observations_db_path(ws)
    tsv_path = observations_tsv_path(ws)
    cfg = resolve_memory_config()
    out: dict[str, Any] = {
        "ok": True,
        "workspace": str(ws),
        "db_path": str(db_path),
        "db_exists": db_path.is_file(),
        "tsv_exists": tsv_path.is_file(),
        "observer_queue_enabled": bool(cfg.observer_queue_enabled),
        "preread_enabled": bool(cfg.preread_enabled),
        "observation_ttl_days": int(cfg.observation_ttl_days),
        "observation_max_rows": int(cfg.observation_max_rows),
        "row_count": 0,
        "distinct_paths": 0,
        "ok_count": 0,
        "fail_count": 0,
        "tool_counts": {},
        "oldest_timestamp": "",
        "newest_timestamp": "",
        "preread_sort": "timestamp_desc",
        "preread_limit": 3,
    }
    if not db_path.is_file():
        return out
    try:
        stats = ObservationStore(db_path).stats()
        out.update(stats)
    except Exception as exc:
        logger.debug("collect observation store stats skipped: %s", exc)
        out["ok"] = False
        out["reason"] = str(exc)
    return out


def format_observation_diagnostic_lines(workspace: Path | None) -> list[str]:
    stats = collect_observation_store_stats(workspace)
    if not stats.get("ok"):
        return []
    lines = ["Observation Store（路径历史 / PreRead）:"]
    lines.append(
        "  写入: "
        f"BUTLER_MEMORY_OBSERVER_QUEUE={'开' if stats.get('observer_queue_enabled') else '关'}"
        f" · PreRead={'开' if stats.get('preread_enabled') else '关'}"
    )
    ttl = int(stats.get("observation_ttl_days") or 0)
    max_rows = int(stats.get("observation_max_rows") or 0)
    lines.append(
        f"  保留: TTL {ttl}d"
        + (f" · 行上限 {max_rows}" if max_rows > 0 else " · 行上限关")
    )
    if stats.get("tsv_exists"):
        lines.append("  ⚠ 遗留 observations.tsv 待迁移（butler memory observations --migrate）")
    rel_db = ".butler/observations.db"
    try:
        ws = Path(str(stats.get("workspace") or ""))
        db_path = Path(str(stats.get("db_path") or ""))
        if db_path.is_file():
            rel_db = str(db_path.relative_to(ws))
    except Exception:
        rel_db = str(stats.get("db_path") or rel_db)
    if not stats.get("db_exists"):
        lines.append(f"  库: 无 ({rel_db or '.butler/observations.db'})")
        return lines
    lines.append(f"  库: {rel_db or '.butler/observations.db'} · 行数 {int(stats.get('row_count') or 0)}")
    paths = int(stats.get("distinct_paths") or 0)
    ok_n = int(stats.get("ok_count") or 0)
    fail_n = int(stats.get("fail_count") or 0)
    if paths:
        lines.append(f"  路径: {paths} · 成功 {ok_n} · 失败 {fail_n}")
    oldest = str(stats.get("oldest_timestamp") or "").strip()
    newest = str(stats.get("newest_timestamp") or "").strip()
    if oldest and newest:
        lines.append(f"  时间: {oldest[:19]} … {newest[:19]}")
    tool_counts = stats.get("tool_counts") or {}
    if isinstance(tool_counts, dict) and tool_counts:
        top = sorted(tool_counts.items(), key=lambda kv: (-int(kv[1]), kv[0]))[:5]
        parts = [f"{name}={count}" for name, count in top]
        lines.append(f"  工具 Top: {', '.join(parts)}")
    lines.append(
        "  PreRead 排序: 路径匹配后按 timestamp 降序取最近 "
        f"{int(stats.get('preread_limit') or 3)} 条（时间序展示）"
    )
    return lines


__all__ = [
    "collect_observation_store_stats",
    "format_observation_diagnostic_lines",
]
