"""Deferred WeChat runtime push queue when iLink rate-limits."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from butler.config import get_butler_home

logger = logging.getLogger(__name__)

_QUEUE_FILE = "runtime/push_queue.jsonl"
_MAX_QUEUE = 50


def _queue_path() -> Path:
    return get_butler_home() / _QUEUE_FILE


def _dedupe_key(title: str, body: str, chat_id: str) -> str:
    raw = f"{title}\n{body}\n{chat_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def enqueue_failed_push(title: str, body: str, *, chat_id: str | None = None) -> None:
    path = _queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cid = (chat_id or "").strip()
    key = _dedupe_key(title[:200], body[:4000], cid)
    row = {
        "ts": time.time(),
        "title": title[:200],
        "body": body[:4000],
        "chat_id": cid,
        "dedupe_key": key,
    }
    lines: list[str] = []
    if path.is_file():
        for ln in path.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                old = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if str(old.get("dedupe_key") or "") == key:
                continue
            lines.append(ln)
    from butler.io.atomic_write import atomic_write_text

    lines.append(json.dumps(row, ensure_ascii=False))
    atomic_write_text(path, "\n".join(lines) + "\n")
    _trim_queue(path)


def _trim_queue(path: Path) -> None:
    if not path.is_file():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) <= _MAX_QUEUE:
        return
    from butler.io.atomic_write import atomic_write_text

    atomic_write_text(path, "\n".join(lines[-_MAX_QUEUE:]) + "\n")


def count_pending_pushes(*, chat_id: str | None = None) -> int:
    """Return number of rows in the push queue (optionally filter by chat_id)."""
    path = _queue_path()
    if not path.is_file():
        return 0
    cid = (chat_id or "").strip()
    if not cid:
        return sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())
    count = 0
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if str(row.get("chat_id") or "").strip() == cid:
            count += 1
    return count


def drain_push_queue(*, max_items: int = 3) -> dict[str, Any]:
    """
    Retry queued pushes (newest first). Called from runtime due / manual ops.
    """
    from butler.runtime.notify import push_runtime_message

    path = _queue_path()
    if not path.is_file():
        return {"drained": 0, "remaining": 0, "sent": 0, "failed": 0}

    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return {"drained": 0, "remaining": 0, "sent": 0, "failed": 0}

    pending = [json.loads(ln) for ln in lines]
    pending.reverse()  # newest first
    to_try = pending[: max(1, max_items)]
    tail = pending[max_items:]

    sent = failed = 0
    retry_later: list[dict[str, Any]] = []
    for item in to_try:
        ok = push_runtime_message(
            item.get("title") or "[Butler]",
            item.get("body") or "",
            chat_id=item.get("chat_id") or None,
        )
        if ok:
            sent += 1
        else:
            failed += 1
            retry_later.append(item)

    rest = retry_later + tail
    rest.reverse()
    if rest:
        from butler.io.atomic_write import atomic_write_text

        atomic_write_text(
            path,
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rest) + "\n",
        )
    else:
        path.unlink(missing_ok=True)

    out = {
        "drained": len(to_try),
        "remaining": len(rest),
        "sent": sent,
        "failed": failed,
    }
    if sent or failed:
        logger.info("Runtime push queue drain: %s", out)
    return out
