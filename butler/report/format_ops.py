"""Report format rendering best-effort helpers (P0-A)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def render_child_session_detail_safe(sk: str, *, max_lines: int) -> str:
    try:
        from butler.core.session_transcript import transcript_enabled

        if not transcript_enabled():
            return (
                f"child_session: {sk}\n"
                "Transcript: 已关闭 (BUTLER_SESSION_TRANSCRIPT=0)\n"
                "提示: 设置环境变量后重发 /详细 --child <sk> 查看子会话"
            )
        from butler.core.transcript_export import build_session_markdown

        body = build_session_markdown(sk, max_lines=max_lines, include_tasks=False)
        if "无 transcript 记录" in body or "BUTLER_SESSION_TRANSCRIPT" in body:
            return (
                f"child_session: {sk}\n"
                "Transcript: 暂无记录 (子会话可能尚未产生事件, 或 jsonl 已被 retention 清掉)\n"
                "提示: 父会话 /任务 行会显示 child_sk; 发 /任务 --task-id <tid> 可反查"
            )
        return f"child_session: {sk}\n\n{body}"
    except Exception as exc:
        logger.debug("child session render skipped: %s", exc)
        return (
            f"child_session: {sk}\n"
            f"渲染失败: {str(exc)[:200]}\n"
            "提示: 检查 transcript.jsonl 是否可读, 或联系 owner"
        )
