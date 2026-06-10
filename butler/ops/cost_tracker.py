"""Session-scoped cost tracker (observation only, not a scheduling input)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

_LOCK = threading.Lock()
_SESSIONS: dict[str, "SessionCost"] = {}


@dataclass
class SessionCost:
    """Accumulated cost metrics for one session."""
    session_key: str
    started_at: float = field(default_factory=time.time)
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls_pim: int = 0
    tool_calls_dev: int = 0
    tool_calls_pm: int = 0
    tool_calls_other: int = 0
    delegate_spawns: int = 0
    model_breakdown: dict[str, list[int]] = field(default_factory=dict)

    def record_llm_call(self, *, input_tokens: int = 0, output_tokens: int = 0, model: str = "") -> None:
        self.llm_calls += 1
        pin = max(0, input_tokens)
        pout = max(0, output_tokens)
        self.input_tokens += pin
        self.output_tokens += pout
        if model:
            if model not in self.model_breakdown:
                self.model_breakdown[model] = [0, 0]
            self.model_breakdown[model][0] += pin
            self.model_breakdown[model][1] += pout
        try:
            from butler.ops.cost_calibration import record_llm_cost_event

            record_llm_cost_event(
                input_tokens=pin,
                output_tokens=pout,
                model=model,
                session_key=self.session_key,
            )
        except Exception:
            pass

    def record_tool_call(self, tool_name: str) -> None:
        from butler.tools.pim_schema import ALL_PIM_TOOLS
        name = (tool_name or "").strip()
        if name in ALL_PIM_TOOLS:
            self.tool_calls_pim += 1
            bucket = "pim"
        elif name in ("delegate_task",):
            self.delegate_spawns += 1
            self.tool_calls_dev += 1
            bucket = "dev"
        elif name in ("run_workflow", "list_workflows", "run_runtime_job", "list_runtime_jobs"):
            self.tool_calls_pm += 1
            bucket = "pm"
        else:
            self.tool_calls_other += 1
            bucket = "other"
        try:
            from butler.ops.cost_calibration import record_tool_cost_event

            record_tool_cost_event(
                tool_name=name,
                bucket=bucket,
                session_key=self.session_key,
            )
        except Exception:
            pass

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def total_tool_calls(self) -> int:
        return self.tool_calls_pim + self.tool_calls_dev + self.tool_calls_pm + self.tool_calls_other

    def format_summary(self) -> str:
        elapsed = time.time() - self.started_at
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)

        total_tc = self.total_tool_calls
        pim_pct = f" ({self.tool_calls_pim * 100 // total_tc}%)" if total_tc else ""
        dev_pct = f" ({self.tool_calls_dev * 100 // total_tc}%)" if total_tc else ""
        pm_pct = f" ({self.tool_calls_pm * 100 // total_tc}%)" if total_tc else ""
        oth_pct = f" ({self.tool_calls_other * 100 // total_tc}%)" if total_tc else ""

        lines = [
            f"📊 会话成本概览（{mins}m{secs}s）",
            f"",
            f"LLM 调用: {self.llm_calls} 次",
            f"  输入 Token: ~{self.input_tokens:,}",
            f"  输出 Token: ~{self.output_tokens:,}",
            f"  合计 Token: ~{self.total_tokens:,}",
        ]

        if self.total_tokens > 0:
            from butler.ops.token_cost_diagnostics import _estimate_cost_usd
            if self.model_breakdown:
                total_est = 0.0
                for m, (m_in, m_out) in sorted(self.model_breakdown.items()):
                    est = _estimate_cost_usd(m_in, m_out, model=m)
                    if est is not None:
                        total_est += est
                        lines.append(f"  {m}: in={m_in:,} out={m_out:,} ~${est:.4f}")
                if total_est > 0:
                    lines.append(f"  合计预估: ~${total_est:.4f}")
            else:
                est = _estimate_cost_usd(self.input_tokens, self.output_tokens)
                if est is not None:
                    lines.append(f"  预估费用: ~${est:.4f}")

        lines += [
            f"",
            f"工具调用: {total_tc} 次",
            f"  PIM 工具: {self.tool_calls_pim}{pim_pct}",
            f"  开发工具: {self.tool_calls_dev}{dev_pct}",
            f"  项目管理: {self.tool_calls_pm}{pm_pct}",
            f"  其他工具: {self.tool_calls_other}{oth_pct}",
            f"",
            f"委派: {self.delegate_spawns} 次",
        ]
        return "\n".join(lines)


def get_session_cost(session_key: str) -> SessionCost:
    with _LOCK:
        if session_key not in _SESSIONS:
            _SESSIONS[session_key] = SessionCost(session_key=session_key)
        return _SESSIONS[session_key]


def reset_session_cost(session_key: str) -> None:
    with _LOCK:
        _SESSIONS.pop(session_key, None)


def format_cost_summary(session_key: str) -> str:
    return get_session_cost(session_key).format_summary()
