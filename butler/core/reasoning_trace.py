"""CoT observability, verify reflect, and plan-mode DoT-lite hooks."""

from __future__ import annotations

import logging
import re
from typing import Any

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_SUMMARY_MAX = 280
_GRAPH_STEP_KINDS = frozenset({"fact", "hypothesis", "step", "risk"})


def reasoning_trace_enabled() -> bool:
    return env_truthy("BUTLER_REASONING_TRACE", default=True)


def plan_reason_graph_enabled() -> bool:
    return env_truthy("BUTLER_PLAN_REASON_GRAPH", default=False)


def summarize_reasoning_text(text: str, *, max_len: int = _SUMMARY_MAX) -> str:
    raw = re.sub(r"\s+", " ", str(text or "").strip())
    if not raw:
        return ""
    if len(raw) <= max_len:
        return raw
    return raw[: max_len - 1].rstrip() + "…"


def _resolve_session_key(explicit: str = "") -> str:
    key = str(explicit or "").strip()
    if key:
        return key
    try:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip() or "default"
    except Exception:
        return "default"


def record_reasoning_step(
    session_key: str,
    *,
    phase: str = "llm",
    summary: str = "",
    tool_intent: str = "",
    iteration: int = 0,
    source: str = "loop",
) -> None:
    if not reasoning_trace_enabled():
        return
    from butler.core.session_transcript import record_reasoning_step as _record

    _record(
        session_key,
        phase=str(phase or "llm")[:32],
        summary=summarize_reasoning_text(summary),
        tool_intent=(tool_intent or "")[:120],
        iteration=max(0, int(iteration)),
        source=str(source or "loop")[:32],
    )


def record_reflect_step(
    session_key: str,
    *,
    trigger: str = "verify_fail",
    cause: str = "",
    strategy: str = "",
    detail: str = "",
    source: str = "delegate",
) -> None:
    if not reasoning_trace_enabled():
        return
    from butler.core.session_transcript import record_reflect_step as _record

    _record(
        session_key,
        trigger=str(trigger or "verify_fail")[:32],
        cause=summarize_reasoning_text(cause, max_len=200),
        strategy=(strategy or "")[:64],
        detail=summarize_reasoning_text(detail, max_len=200),
        source=str(source or "delegate")[:32],
    )


def maybe_record_llm_reasoning(loop: Any, response: Any, *, iteration: int = 0) -> None:
    """Persist a short reasoning summary after each LLM response."""
    if not reasoning_trace_enabled():
        return
    session_key = _resolve_session_key(str(getattr(loop, "_session_key", "") or ""))
    reasoning = summarize_reasoning_text(str(getattr(response, "reasoning", "") or ""))
    content = summarize_reasoning_text(str(getattr(response, "content", "") or ""))
    summary = reasoning or content
    if not summary:
        return
    tool_calls = getattr(response, "tool_calls", None) or []
    tool_intent = ""
    if tool_calls:
        names = [str(getattr(tc, "name", "") or "") for tc in tool_calls[:4]]
        tool_intent = ",".join(n for n in names if n)
    record_reasoning_step(
        session_key,
        phase="tool_plan" if tool_intent else "text",
        summary=summary,
        tool_intent=tool_intent,
        iteration=iteration,
        source="loop",
    )


def record_verify_fail_reflect(state: Any, verify_result: Any) -> None:
    """Unified reflect transcript row after dev verify failure."""
    session_key = _resolve_session_key(
        str(getattr(state, "session_key", "") or getattr(state, "_session_key", "") or "")
    )
    diags = getattr(verify_result, "diagnostics", None) or []
    messages: list[str] = []
    for diag in diags[:4]:
        msg = str(getattr(diag, "message", "") or getattr(diag, "rule", "") or "")
        if msg:
            messages.append(msg)
    tail = str(getattr(verify_result, "output_tail", "") or "")
    if tail and not messages:
        messages.append(tail[:160])
    cause = "; ".join(messages) or "verify failed"
    strategy = str(getattr(state, "_last_fix_hint", "") or "")
    if not strategy:
        try:
            from butler.dev_engine.fix_strategy import enrich_fix_hint, suggest_fix_action

            level = suggest_fix_action(diags, state)
            strategy = enrich_fix_hint(level, state)
        except Exception:
            strategy = "retry_fix"
    record_reflect_step(
        session_key,
        trigger="verify_fail",
        cause=cause,
        strategy=strategy,
        detail=f"fix_count={getattr(state, 'fix_count', 0)}",
        source="dev_engine",
    )


def record_stuck_reflect(
    loop: Any,
    stuck_message: str,
    *,
    trigger: str = "guardrail_stuck",
    source: str = "loop",
) -> None:
    """Record reflect_step when Loop enters STUCK (guardrail / doom loop)."""
    session_key = _resolve_session_key(str(getattr(loop, "_session_key", "") or ""))
    cause = summarize_reasoning_text(stuck_message, max_len=200) or "loop stuck"
    strategy = "ask_clarification_or_narrow_scope"
    code = ""
    guardrails = getattr(loop, "_guardrails", None)
    dec = getattr(guardrails, "halt_decision", None) if guardrails else None
    if dec is not None:
        code = str(getattr(dec, "code", "") or "")
        if code == "doom_loop":
            trigger = "doom_loop"
            strategy = "approve_once_or_change_approach"
        elif code.startswith("ping_pong"):
            trigger = "ping_pong"
            strategy = "avoid_repeat_tool_pattern"
    record_reflect_step(
        session_key,
        trigger=trigger,
        cause=cause,
        strategy=strategy,
        detail=code[:64],
        source=source,
    )


def maybe_record_guardrail_reflect(
    loop: Any,
    decision: Any,
    tool_name: str,
) -> None:
    """Best-effort reflect when doom_loop blocks a tool call."""
    if decision is None:
        return
    code = str(getattr(decision, "code", "") or "")
    action = str(getattr(decision, "action", "") or "")
    if code != "doom_loop" or action not in ("ask", "block"):
        return
    msg = str(getattr(decision, "message", "") or "").strip()
    record_stuck_reflect(
        loop,
        msg or f"doom_loop on {tool_name}",
        trigger="doom_loop",
        source="guardrail",
    )


def record_doom_loop_reflect(
    session_key: str,
    message: str,
    *,
    tool_name: str = "",
) -> None:
    if not reasoning_trace_enabled():
        return
    record_reflect_step(
        session_key,
        trigger="doom_loop",
        cause=summarize_reasoning_text(message, max_len=200),
        strategy="approve_once_or_change_approach",
        detail=(tool_name or "")[:64],
        source="guardrail",
    )

def maybe_sync_plan_step_to_graph(
    session_key: str,
    *,
    title: str = "",
    step_kind: str = "",
    assumption: str = "",
    evidence: str = "",
    detail: str = "",
) -> None:
    if not plan_reason_graph_enabled():
        return
    kind = str(step_kind or "").strip().lower()
    if kind not in _GRAPH_STEP_KINDS:
        return
    try:
        from butler.core.plan_reason_graph import append_node
        from butler.plan.mode import is_plan_mode

        if not is_plan_mode(session_key):
            return
        node = append_node(
            session_key,
            text=(detail or title or "")[:500],
            role=kind,
            title=title,
            assumption=assumption,
            evidence=evidence,
        )
        from butler.core.session_transcript import record_reason_graph_event

        record_reason_graph_event(
            session_key,
            action="node_added",
            node_id=str(node.get("id") or ""),
            role=kind,
            preview=(title or detail or "")[:120],
        )
    except Exception as exc:
        logger.debug("plan reason graph sync skipped: %s", exc)


def get_plan_mode_graph_appendix() -> str:
    if not plan_reason_graph_enabled():
        return ""
    return (
        "\n\n### 推理图（DoT-lite，opt-in）\n"
        "规划时按 **事实 / 假设 / 步骤 / 风险** 四类记录；系统会写入会话 "
        "`reason_graph.json` 与 transcript。\n"
        "- **fact**：已从代码/文档确认的事实（附 evidence 路径或命令）\n"
        "- **hypothesis**：待验证假设（附 assumption 与验证方式）\n"
        "- **step**：可执行步骤（含文件路径）\n"
        "- **risk**：风险与回滚点\n"
        "在 plan 正文用同级标题标注类型即可；无需手写 JSON。"
    )


def format_reasoning_diagnostic_lines(session_key: str) -> list[str]:
    if not reasoning_trace_enabled():
        return []
    try:
        from butler.core.session_transcript import load_transcript_tail, transcript_enabled
    except Exception:
        return []
    if not transcript_enabled():
        return []
    rows = load_transcript_tail(session_key, max_lines=80)
    reasoning = [r for r in rows if r.get("type") == "reasoning_step"]
    reflects = [r for r in rows if r.get("type") == "reflect_step"]
    graph_line: str | None = None
    if plan_reason_graph_enabled():
        try:
            from butler.core.plan_reason_graph import summarize_graph

            stats = summarize_graph(session_key)
            if stats.get("nodes"):
                graph_line = (
                    f"Plan 推理图: {stats.get('nodes', 0)} 节点 · {stats.get('edges', 0)} 边"
                )
        except Exception:
            pass
    if not reasoning and not reflects and not graph_line:
        return []
    lines: list[str] = []
    if reasoning or reflects:
        lines.append(
            f"推理摘要: 近 {len(rows)} 条 transcript 中含 reasoning={len(reasoning)} reflect={len(reflects)}",
        )
    if reasoning:
        last = reasoning[-1]
        payload = last.get("payload") if isinstance(last.get("payload"), dict) else last
        summary = str(payload.get("summary") or "")[:160]
        phase = str(payload.get("phase") or "")
        if summary:
            lines.append(f"最近推理({phase}): {summary}")
    if reflects:
        last_r = reflects[-1]
        payload = last_r.get("payload") if isinstance(last_r.get("payload"), dict) else last_r
        cause = str(payload.get("cause") or "")[:120]
        strategy = str(payload.get("strategy") or "")[:64]
        if cause or strategy:
            lines.append(f"最近反思: {cause} → 策略 {strategy or '-'}")
    if graph_line:
        lines.append(graph_line)
    return lines


__all__ = [
    "format_reasoning_diagnostic_lines",
    "get_plan_mode_graph_appendix",
    "maybe_record_guardrail_reflect",
    "maybe_record_llm_reasoning",
    "maybe_sync_plan_step_to_graph",
    "plan_reason_graph_enabled",
    "reasoning_trace_enabled",
    "record_doom_loop_reflect",
    "record_reflect_step",
    "record_reasoning_step",
    "record_stuck_reflect",
    "record_verify_fail_reflect",
    "summarize_reasoning_text",
]
