"""Persist daily token usage for /诊断 (cc-switch subset)."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, cast

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)


def usage_persist_enabled() -> bool:
    return bool(env_truthy("BUTLER_USAGE_PERSIST", default=True))


def _ledger_path() -> Path:
    from butler.config import get_butler_home

    return cast(Path, get_butler_home()) / "usage" / f"{date.today().isoformat()}.jsonl"


def record_usage_snapshot(
    *,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cached_tokens: int = 0,
    provider: str = "",
    model: str = "",
) -> None:
    if not usage_persist_enabled():
        return
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "cached_tokens": int(cached_tokens or 0),
        "provider": str(provider or "")[:32],
        "model": str(model or "")[:64],
    }
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.debug("usage ledger write skipped: %s", exc)


def summarize_today_usage() -> dict[str, Any]:
    path = _ledger_path()
    if not path.is_file():
        return {}
    prompt = completion = cached = 0
    lines = 0
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                prompt += int(row.get("prompt_tokens") or 0)
                completion += int(row.get("completion_tokens") or 0)
                cached += int(row.get("cached_tokens") or 0)
                lines += 1
    except OSError:
        return {}
    total_in = prompt + cached
    cache_pct = (cached / total_in * 100.0) if total_in > 0 else 0.0
    return {
        "lines": lines,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_tokens": cached,
        "cache_hit_pct": round(cache_pct, 1),
    }


def format_usage_ledger_lines() -> list[str]:
    snap = summarize_today_usage()
    if not snap:
        return []
    return [
        "今日用量落盘:",
        f"  采样行={snap.get('lines', 0)} "
        f"in={snap.get('prompt_tokens', 0)} "
        f"out={snap.get('completion_tokens', 0)} "
        f"cached={snap.get('cached_tokens', 0)} "
        f"cache≈{snap.get('cache_hit_pct', 0)}%",
    ]


__all__ = [
    "format_usage_ledger_lines",
    "record_usage_snapshot",
    "summarize_today_usage",
    "usage_persist_enabled",
]
