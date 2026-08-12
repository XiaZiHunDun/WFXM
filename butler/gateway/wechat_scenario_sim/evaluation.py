from __future__ import annotations

from typing import Any

from .schema import ScenarioCase
from .utils import _any_tool_in_list, _tool_in_list, resolve_handler_session_key


def evaluation_reply_text(
    handler: Any,
    *,
    owner_id: str,
    session_key: str,
    reply: str,
    tools: list[str],
    platform: str = "wechat",
) -> str:
    # Lazy imports to break circular dependency:
    # butler.tools.registry → butler.core → butler.core.agent_loop
    # → butler.ops → butler.tools.registry
    from butler.core.session_epoch import load_epoch_transcript_rows
    from butler.gateway.outbound_files import expand_reply_with_wechat_attachments
    from butler.gateway.wechat_scenario_sim_ops import delegate_enrichment_imports_ready
    from butler.report import get_last_report

    delegated = _any_tool_in_list(("delegate_task",), tools) or any(
        mark in reply for mark in ("代理已完成", "代理未能", "委派", "task_")
    )

    if not delegated:
        return str(expand_reply_with_wechat_attachments(reply))
    if not delegate_enrichment_imports_ready():
        return reply
    canonical = resolve_handler_session_key(
        handler,
        owner_id=owner_id,
        session_key=session_key,
        platform=platform,
    )
    report = get_last_report(canonical)
    if report is None:
        return reply
    chunks: list[str] = [reply]
    summary = (report.summary or "").strip()
    if summary and summary not in reply:
        chunks.append(summary)
    child_sk = (report.child_session_key or "").strip()
    if child_sk:
        for row in reversed(load_epoch_transcript_rows(child_sk, max_lines=80)):
            if str(row.get("type") or "") != "assistant":
                continue
            text = str(row.get("content_preview") or row.get("content") or "").strip()
            if text and text not in reply and text not in (summary or ""):
                chunks.append(text)
            break
    merged = "\n\n".join(chunks) if len(chunks) > 1 else reply
    return str(expand_reply_with_wechat_attachments(merged))


def _delegate_evidence_in_reply(reply: str) -> bool:
    return any(
        mark in reply
        for mark in ("委派", "代理已完成", "代理未能", "task_", "📎 委派")
    )


def evaluate_scenario_case(
    tools: list[str],
    reply: str,
    case: ScenarioCase,
    *,
    strict: bool = False,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for bad in case.reject_reply_any:
        if bad in reply:
            errors.append(f"reply must not contain {bad!r}")
    for tool in case.forbid_tools:
        if _tool_in_list(tool, tools):
            errors.append(f"forbidden tool {tool}")
    if case.expect_reply_any:
        if not any(needle in reply for needle in case.expect_reply_any):
            msg = f"reply missing any of {case.expect_reply_any}"
            if case.soft:
                warnings.append(msg)
            else:
                errors.append(msg)
    if case.expect_tools_any and not _any_tool_in_list(case.expect_tools_any, tools):
        msg = f"expected tools any of {case.expect_tools_any}, got {tools}"
        delegate_ok = (
            _any_tool_in_list(("delegate_task",), case.expect_tools_any)
            and _delegate_evidence_in_reply(reply)
        )
        if (strict or case.require_tools) and not case.soft and not delegate_ok:
            errors.append(msg)
        elif not delegate_ok:
            warnings.append(msg)
    if case.prefer_tools_any and not _any_tool_in_list(case.prefer_tools_any, tools):
        direct_ok = bool(case.expect_reply_any) and any(x in reply for x in case.expect_reply_any)
        msg = f"preferred tools {case.prefer_tools_any}, got {tools}"
        if strict and not direct_ok and not case.soft:
            errors.append(msg)
        else:
            warnings.append(msg)
    return errors, warnings


def evaluate_outbound_capture(
    capture_bodies: list[str],
    case: ScenarioCase,
) -> list[str]:
    errors: list[str] = []
    count = len(capture_bodies)
    if case.min_outbound_messages and count < case.min_outbound_messages:
        errors.append(
            f"expected >= {case.min_outbound_messages} outbound messages, got {count}"
        )
    if case.expect_outbound_any:
        joined = "\n".join(capture_bodies)
        if not any(needle in joined for needle in case.expect_outbound_any):
            errors.append(f"outbound missing any of {case.expect_outbound_any}")
    return errors
