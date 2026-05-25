"""Extended tool-loop detectors (OpenClaw tool-loop-detection subset)."""

from __future__ import annotations

import json
import os
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any, Mapping

from butler.tool_guardrails import ToolCallSignature

_POLL_TOOLS = frozenset({
    "list_runtime_jobs",
    "butler_recall",
    "session_todos_list",
})


@dataclass(frozen=True)
class LoopDetectDecision:
    stuck: bool
    level: str  # warning | critical
    detector: str
    message: str
    count: int = 0


def enabled_detectors() -> frozenset[str]:
    raw = os.getenv(
        "BUTLER_TOOL_LOOP_DETECTORS",
        "ping_pong,poll,circuit",
    ).strip().lower()
    if raw in ("0", "off", "false", "none"):
        return frozenset()
    return frozenset(x.strip() for x in raw.split(",") if x.strip())


def circuit_breaker_limit() -> int:
    try:
        return max(10, int(os.getenv("BUTLER_TOOL_LOOP_CIRCUIT_LIMIT", "40")))
    except ValueError:
        return 40


def _result_fingerprint(result: str) -> str:
    text = (result or "").strip()[:500]
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return json.dumps(obj, sort_keys=True, ensure_ascii=False)[:200]
    except json.JSONDecodeError:
        pass
    return text[:200]


class ToolLoopDetector:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._history: deque[tuple[str, str, str]] = deque(maxlen=30)
        self._result_fps: deque[tuple[str, str]] = deque(maxlen=20)
        self._total_calls = 0
        self._last_detector = ""

    def reset_for_turn(self) -> None:
        with self._lock:
            self._history.clear()
            self._result_fps.clear()
            self._total_calls = 0
            self._last_detector = ""

    def record_call(self, tool_name: str, args_hash: str, result: str = "") -> None:
        with self._lock:
            self._total_calls += 1
            self._history.append((tool_name, args_hash, _result_fingerprint(result)))
            if tool_name in _POLL_TOOLS:
                self._result_fps.append((tool_name, _result_fingerprint(result)))

    def check_before_call(
        self,
        tool_name: str,
        args: Mapping[str, Any] | None,
    ) -> LoopDetectDecision | None:
        enabled = enabled_detectors()
        if not enabled:
            return None
        sig = ToolCallSignature.from_call(tool_name, args)
        with self._lock:
            if "circuit" in enabled and self._total_calls >= circuit_breaker_limit():
                self._last_detector = "circuit"
                return LoopDetectDecision(
                    stuck=True,
                    level="critical",
                    detector="circuit",
                    message=f"单轮工具调用已达上限 ({circuit_breaker_limit()})",
                    count=self._total_calls,
                )
            if "ping_pong" in enabled:
                dec = self._check_ping_pong(sig.tool_name, sig.args_hash)
                if dec is not None:
                    self._last_detector = dec.detector
                    return dec
            if "poll" in enabled and tool_name in _POLL_TOOLS:
                dec = self._check_poll_no_progress(tool_name)
                if dec is not None:
                    self._last_detector = dec.detector
                    return dec
        return None

    def _check_ping_pong(self, tool_name: str, args_hash: str) -> LoopDetectDecision | None:
        if len(self._history) < 4:
            return None
        recent = list(self._history)[-6:]
        names = [r[0] for r in recent]
        if len(set(names)) != 2:
            return None
        hashes = [r[1] for r in recent]
        if len(set(hashes)) > 3:
            return None
        alt = names[0] != names[1]
        if not all(names[i] != names[i + 1] for i in range(len(names) - 1)):
            return None
        if not alt:
            return None
        label = " <-> ".join(sorted(set(names)))
        if len(recent) >= 6:
            return LoopDetectDecision(
                stuck=True,
                level="critical",
                detector="ping_pong",
                message=f"工具乒乓循环: {label}",
                count=len(recent),
            )
        return LoopDetectDecision(
            stuck=True,
            level="warning",
            detector="ping_pong_soft_nudge",
            message=f"疑似工具乒乓: {label}。请收敛策略或 delegate_yield。",
            count=len(recent),
        )

    def _check_poll_no_progress(self, tool_name: str) -> LoopDetectDecision | None:
        same = [fp for name, fp in self._result_fps if name == tool_name]
        if len(same) < 4:
            return None
        if len(set(same[-4:])) == 1:
            return LoopDetectDecision(
                stuck=True,
                level="warning",
                detector="poll",
                message=f"轮询工具 {tool_name} 连续无进展，请改用 delegate_yield 或读 task 状态",
                count=len(same),
            )
        return None

    def last_detector_label(self) -> str:
        with self._lock:
            return self._last_detector or ""


_GLOBAL = ToolLoopDetector()


def get_tool_loop_detector() -> ToolLoopDetector:
    return _GLOBAL
