"""Async delegate tool-result JSON (kept out of delegate_job to break import cycles)."""

from __future__ import annotations

import json
from typing import Any

from butler.tools.delegate_impl import _delegate_role_label


def build_async_delegate_tool_result(
    *,
    task_id: str,
    child_session_key: str,
    role: str,
    task_preview: str,
    category: str = "",
) -> str:
    role_label = _delegate_role_label(role)
    payload: dict[str, Any] = {
        "success": True,
        "background": True,
        "async": True,
        "task_id": task_id,
        "child_session_key": child_session_key,
        "headline": f"{role_label}已接单，后台执行中",
        "summary": (
            "进度：已提交 → 执行中 → 完成后微信通知。\n"
            "可查：/任务（状态）· /详细（完整报告）· /继续（若中断）"
        ),
        "message": (
            f"已委派 {role_label}（task_id={task_id}）。"
            "完成后会单独通知；您可继续其它对话。"
        ),
    }
    if category:
        payload["category"] = category
    if task_preview:
        payload["task_preview"] = task_preview[:200]
    return json.dumps(payload, ensure_ascii=False)


__all__ = ["build_async_delegate_tool_result"]
