"""DevEnginePlugin — injects DevState context into LLM messages.

Registered as a LoopPlugin when role=dev and BUTLER_DEV_ENGINE=1.
Implements:
  - before_model: inject dev_state_context_block + fix hints
  - after_tools: inject diagnostics after verify failures
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class DevEnginePlugin:
    """Loop plugin that injects DevState into LLM context (DD1/DD2)."""

    def __init__(self, session_key: str = "_default"):
        self._session_key = session_key

    def before_model(self, messages: list[dict]) -> list[dict]:
        """Inject DevState summary as a system-level context block."""
        try:
            from butler.dev_engine.dev_context import dev_state_context_block
            from butler.dev_engine.dev_tools import (
                _active_states,
                dev_engine_enabled,
                diagnostics_inject_enabled,
            )

            if not dev_engine_enabled():
                return messages

            try:
                from butler.core.read_state import rehydrate_read_state_from_messages

                rehydrate_read_state_from_messages(
                    messages, session_key=self._session_key,
                )
            except Exception as exc:
                logger.debug("read_state rehydrate skipped: %s", exc)

            state = _active_states.get(self._session_key)
            if state is None:
                return messages

            block = dev_state_context_block(state)
            if not block or not block.strip():
                return messages

            # DE-3: STUCK injects hard termination signal
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
        except Exception as exc:
            logger.debug("DevEnginePlugin before_model failed: %s", exc)
            return messages

    def after_tools(
        self,
        messages: list[dict],
        *,
        tool_stats: Any = None,
    ) -> list[dict]:
        """After tool batch, inject diagnostic summary if verify failed."""
        try:
            from butler.dev_engine.dev_tools import (
                _active_states,
                dev_engine_enabled,
                diagnostics_inject_enabled,
            )

            if not dev_engine_enabled() or not diagnostics_inject_enabled():
                return messages

            state = _active_states.get(self._session_key)
            if state is None:
                return messages

            from butler.dev_engine.dev_state import VerifyStatus

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

            out = list(messages)
            out.append({
                "role": "system",
                "content": "\n".join(lines),
            })
            return out
        except Exception as exc:
            logger.debug("DevEnginePlugin after_tools failed: %s", exc)
            return messages


def create_dev_engine_plugin(session_key: str = "_default") -> DevEnginePlugin:
    return DevEnginePlugin(session_key=session_key)
