"""Best-effort / fail-closed helpers for OpenCode bridge (P0-A)."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable
from typing import Any, cast

from butler.core.best_effort import safe_best_effort


def http_health_available_safe(url: str) -> bool:
    def _run() -> bool:
        import httpx

        resp = httpx.get(f"{url}/health", timeout=5)
        return cast(bool, resp.status_code == 200)

    return safe_best_effort(_run, label="opencode.http_health", default=False) is True


def run_subprocess_opencode_task(
    *,
    cmd: list[str],
    timeout: int,
    t0: float,
    mode_value: str,
    parse_events: Callable[[str], list[Any]],
    extract_text: Callable[[list[Any]], str],
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ},
        )
        elapsed = time.time() - t0
        events = parse_events(result.stdout)
        text = extract_text(events)

        if result.returncode != 0 and not text:
            err = (result.stderr or "").strip()
            return {
                "ok": False,
                "result": f"OpenCode exited with code {result.returncode}: {err[:500]}",
                "mode": mode_value,
                "elapsed_seconds": round(elapsed, 2),
                "events_count": len(events),
            }

        return {
            "ok": True,
            "result": text[:10000] if text else "(no output)",
            "mode": mode_value,
            "elapsed_seconds": round(elapsed, 2),
            "events_count": len(events),
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "result": f"OpenCode 执行超时 ({timeout}s)",
            "mode": mode_value,
            "elapsed_seconds": timeout,
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "result": f"OpenCode 未安装或不在 PATH 中 (looked for: {cmd[0]})",
            "mode": mode_value,
            "elapsed_seconds": 0,
        }
    except Exception as exc:
        return {
            "ok": False,
            "result": f"OpenCode 异常: {exc}",
            "mode": mode_value,
            "elapsed_seconds": round(time.time() - t0, 2),
        }


def run_http_opencode_task(
    run: Callable[[], dict[str, Any]],
    *,
    mode_value: str,
    t0: float,
) -> dict[str, Any]:
    try:
        return run()
    except Exception as exc:
        return {
            "ok": False,
            "result": f"OpenCode HTTP 异常: {exc}",
            "mode": mode_value,
            "elapsed_seconds": round(time.time() - t0, 2),
        }


def poll_session_status_safe(
    poll: Callable[[], str | None],
) -> str | None:
    result = safe_best_effort(poll, label="opencode.http_poll", default=None)
    return str(result) if isinstance(result, str) else None


def fetch_session_transcript_safe(fetch: Callable[[], str]) -> str:
    result = safe_best_effort(fetch, label="opencode.http_transcript", default=None)
    if isinstance(result, str) and result:
        return result
    return "(failed to fetch transcript)"
