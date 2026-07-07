"""DevEngine loop plugin best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def _insert_before_last_user(messages: list[dict[str, Any]], content: str) -> list[dict[str, Any]]:
    out = list(messages)
    last_user = -1
    for i in range(len(out) - 1, -1, -1):
        if out[i].get("role") == "user":
            last_user = i
            break
    insert_at = last_user if last_user >= 0 else len(out)
    out.insert(insert_at, {"role": "system", "content": content})
    return out


def rehydrate_read_state_safe(session_key: str, messages: list[dict[str, Any]]) -> None:
    def _run() -> None:
        from butler.core.read_state import rehydrate_read_state_from_messages

        rehydrate_read_state_from_messages(messages, session_key=session_key)

    safe_best_effort(_run, label="loop_plugin.rehydrate_read_state", default=None)


def inject_dev_before_model_safe(session_key: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        from butler.dev_engine.dev_context import dev_state_context_block
        from butler.dev_engine.dev_tools import (
            _active_states,
            dev_engine_enabled,
        )

        if not dev_engine_enabled():
            return messages

        rehydrate_read_state_safe(session_key, messages)

        state = _active_states.get(session_key)
        if state is None:
            return messages

        block = dev_state_context_block(state)
        if not block or not block.strip():
            return messages

        if state.is_terminal:
            block += (
                "\n\n⚠️ 开发循环已终止"
                f"（状态: {state.phase.value}）。"
                "不要再调用任何编辑或验证工具。"
                "请立即生成最终回复，总结已完成的工作和剩余问题。"
            )

        fix_hint = getattr(state, "_last_fix_hint", None)
        if fix_hint:
            block += f"\nfix_recommendation: {fix_hint}"
            state._last_fix_hint = None

        inject_msg = {"role": "system", "content": block}

        out = list(messages)
        sys_end = 0
        for i, m in enumerate(out):
            if m.get("role") == "system":
                sys_end = i + 1
            else:
                break
        out.insert(sys_end, inject_msg)
        return out

    result = safe_best_effort(
        _run,
        label="loop_plugin.before_model",
        default=messages,
    )
    return list(result) if isinstance(result, list) else list(messages)


def inject_dev_after_tools_safe(session_key: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        from butler.dev_engine.dev_state import VerifyStatus
        from butler.dev_engine.dev_tools import (
            _active_states,
            dev_engine_enabled,
            diagnostics_inject_enabled,
        )
        from butler.dev_engine.loop_plugin import verify_fix_pin_enabled

        if not dev_engine_enabled() or not diagnostics_inject_enabled():
            return messages

        state = _active_states.get(session_key)
        if state is None:
            return messages

        if state.verify_result.status != VerifyStatus.FAIL:
            return messages

        lines = ["<dev-verify-feedback>"]
        if state.diagnostics:
            lines.append("diagnostics:")
            for d in state.diagnostics[:10]:
                lines.append(
                    f"  {d.file}:{d.line} [{d.severity.value}] {d.message}"
                )
        else:
            vr = state.verify_result
            lines.append(
                f"verify_failed: command={vr.command or 'unknown'}"
                f" exit_code={vr.exit_code}"
            )
            tail = getattr(vr, "output_tail", "") or ""
            if tail.strip():
                lines.append("output_tail:")
                lines.append(tail.strip()[-1200:])
        fix_hint = getattr(state, "_last_fix_hint", None)
        if fix_hint:
            lines.append(f"fix_recommendation: {fix_hint}")
            state._last_fix_hint = None
        lines.append("</dev-verify-feedback>")

        block = "\n".join(lines)
        if verify_fix_pin_enabled():
            return _insert_before_last_user(messages, block)
        out = list(messages)
        out.append({"role": "system", "content": block})
        return out

    result = safe_best_effort(
        _run,
        label="loop_plugin.after_tools",
        default=messages,
    )
    return list(result) if isinstance(result, list) else list(messages)
