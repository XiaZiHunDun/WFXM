"""WeChat slash: /评价 — resolve pending outcome log rows."""

from __future__ import annotations

from typing import Any

from butler.gateway.owner_gate import is_gateway_owner, owner_required_message


def handle_outcome_command(
    orchestrator: Any,
    arg: str,
    *,
    platform: str = "",
    external_id: str | None = None,
    session_key: str = "",
) -> str | None:
    """
    /评价 [row_id] <结果值> [反思一句]
    /评价 list — 列出 pending

    Sprint 11 SEC-11-6: 写入 experiments/outcomes.py，需 Owner 守门避免
    污染实验评估日志。
    """
    # Sprint 11 SEC-11-6: 非 Owner 一律拒绝
    if not is_gateway_owner(
        platform=platform, external_id=external_id, session_key=session_key
    ):
        return str(owner_required_message())
    text = (arg or "").strip()
    proj = orchestrator.project_manager.get_current(session_key=session_key)
    if proj is None:
        return "请先 /switch 到项目后再使用 /评价。"
    from pathlib import Path

    ws = Path(proj.workspace)
    from butler.experiments.outcomes import list_pending, resolve_outcome

    if text.lower() in ("list", "列表", "pending", "待处理"):
        rows = list_pending(ws, project=str(proj.name or ""), limit=10)
        if not rows:
            return "当前项目无 pending 结果记录。"
        lines = ["待评价结果（发 /评价 <row_id> <结果> [反思]）:"]
        for r in rows:
            lines.append(
                f"  {r.get('row_id')} | {r.get('subject')} | "
                f"{r.get('hypothesis', '')[:40]}"
            )
        return "\n".join(lines)

    parts = text.split(maxsplit=2)
    if len(parts) < 2:
        return (
            "用法:\n"
            "  /评价 list — 待处理列表\n"
            "  /评价 <row_id> <结果值> [反思]"
        )

    row_id = parts[0]
    outcome_value = parts[1]
    reflection = parts[2] if len(parts) > 2 else ""

    resolved = resolve_outcome(
        ws,
        row_id=row_id,
        outcome_value=outcome_value,
        reflection=reflection,
        project=str(proj.name or ""),
    )
    if resolved is None:
        return f"未找到 pending 记录: {row_id}"
    ref = str(resolved.get("reflection") or "")[:200]
    return f"已记录结果 {outcome_value}。\n反思: {ref}"
