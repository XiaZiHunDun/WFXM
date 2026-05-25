"""Persisted goal loop state for Owner /循环 (OMO ralph-loop subset; default off)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def goal_loop_globally_enabled() -> bool:
    return os.getenv("BUTLER_GOAL_LOOP", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _state_path(session_key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_:" else "_" for c in session_key.strip())
    return Path(os.path.expanduser("~/.butler/sessions")) / safe / "goal_loop.json"


def load_state(session_key: str) -> dict[str, Any] | None:
    path = _state_path(session_key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_state(session_key: str, state: dict[str, Any]) -> None:
    path = _state_path(session_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_state(session_key: str) -> None:
    path = _state_path(session_key)
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def is_goal_loop_active(session_key: str) -> bool:
    st = load_state(session_key)
    return bool(st and st.get("active"))


def goal_token_budget_default() -> int:
    import os

    try:
        return max(0, int(os.getenv("BUTLER_GOAL_TOKEN_BUDGET", "") or "0"))
    except ValueError:
        return 0


def start_goal_loop(
    session_key: str,
    prompt: str,
    *,
    max_iterations: int = 5,
    token_budget: int | None = None,
) -> str:
    prompt = (prompt or "").strip()
    if not prompt:
        return "用法: /循环 <目标描述>"
    budget = goal_token_budget_default() if token_budget is None else max(0, int(token_budget))
    save_state(session_key, {
        "active": True,
        "prompt": prompt,
        "iteration": 0,
        "max_iterations": max(1, min(max_iterations, 20)),
        "token_budget": budget,
        "tokens_used": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
    })
    budget_note = f"，token 预算 {budget}" if budget > 0 else ""
    return f"已启动目标循环（最多 {max_iterations} 轮{budget_note}）。目标: {prompt[:200]}"


def stop_goal_loop(session_key: str) -> str:
    clear_state(session_key)
    return "已停止目标循环。"


def record_goal_tokens(session_key: str, tokens: int) -> bool:
    """Accumulate billable tokens; return True if budget exhausted."""
    st = load_state(session_key)
    if not st or not st.get("active"):
        return False
    budget = int(st.get("token_budget") or 0)
    if budget <= 0:
        return False
    used = int(st.get("tokens_used") or 0) + max(0, int(tokens))
    st["tokens_used"] = used
    save_state(session_key, st)
    return used >= budget


def goal_budget_exhausted_message(session_key: str) -> str | None:
    st = load_state(session_key)
    if not st or not st.get("active"):
        return None
    budget = int(st.get("token_budget") or 0)
    used = int(st.get("tokens_used") or 0)
    if budget > 0 and used >= budget:
        clear_state(session_key)
        return (
            f"目标循环已停止：token 预算已用尽（{used:,} / {budget:,}）。"
            "可重新 /循环 设定目标。"
        )
    return None


def next_goal_message(session_key: str) -> str | None:
    st = load_state(session_key)
    if not st or not st.get("active"):
        return None
    exhausted = goal_budget_exhausted_message(session_key)
    if exhausted:
        return None
    iteration = int(st.get("iteration") or 0)
    max_iter = int(st.get("max_iterations") or 5)
    if iteration >= max_iter:
        clear_state(session_key)
        return None
    st["iteration"] = iteration + 1
    save_state(session_key, st)
    prompt = str(st.get("prompt") or "")
    budget = int(st.get("token_budget") or 0)
    used = int(st.get("tokens_used") or 0)
    budget_line = ""
    if budget > 0:
        budget_line = f"\nToken 预算: {used:,} / {budget:,}"
    return (
        f"[目标循环 {iteration + 1}/{max_iter}] 继续推进以下目标:\n{prompt}\n"
        f"{budget_line}\n"
        "若已完成请明确说明并停止调用工具。"
    ).strip()


def maybe_run_goal_continuation(
    loop: Any,
    result: Any,
    session_key: str,
    *,
    run_fn: Any,
) -> Any:
    """After a completed turn, optionally inject another user message from goal loop."""
    if not is_goal_loop_active(session_key):
        return result
    from butler.core.agent_loop import LoopStatus

    if getattr(result, "status", None) != LoopStatus.COMPLETED:
        return result
    try:
        tokens = int(getattr(result, "total_tokens", 0) or 0)
        if tokens > 0:
            record_goal_tokens(session_key, tokens)
    except Exception:
        pass
    exhausted_msg = goal_budget_exhausted_message(session_key)
    if exhausted_msg:
        result.final_response = (
            (getattr(result, "final_response", "") or "").strip()
            + "\n\n"
            + exhausted_msg
        ).strip()
        diag = dict(getattr(result, "diagnostics", {}) or {})
        diag["goal_loop_budget_exhausted"] = True
        result.diagnostics = diag
        return result
    msg = next_goal_message(session_key)
    if not msg:
        return result
    next_result = run_fn(msg)
    diag = dict(getattr(result, "diagnostics", {}) or {})
    diag.update(getattr(next_result, "diagnostics", {}) or {})
    diag["goal_loop_continuation"] = True
    next_result.diagnostics = diag
    return next_result
