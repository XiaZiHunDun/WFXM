"""Tool-call loop guardrail primitives for Butler v3.

Two-phase (before_call + after_call) loop detector that tracks repeated
failures and non-progressing idempotent reads within a single agent turn.

Actions: allow, warn, block, halt.

Ported from Butler v1, adapted for Hermes tool naming.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from typing import Any, Mapping

IDEMPOTENT_TOOLS = frozenset({
    "read_file",
    "search_code",
    "search_files",
    "list_directory",
    "git_status",
    "git_diff",
    "git_log",
    "skills_list",
    "skill_view",
    "butler_recall",
})

MUTATING_TOOLS = frozenset({
    "run_shell",
    "terminal",
    "write_file",
    "edit_file",
    "patch",
    "git_add",
    "git_commit",
})


@dataclass(frozen=True)
class GuardrailConfig:
    warnings_enabled: bool = True
    hard_stop_enabled: bool = True
    exact_failure_warn_after: int = 2
    exact_failure_block_after: int = 5
    same_tool_failure_warn_after: int = 3
    same_tool_failure_halt_after: int = 8
    no_progress_warn_after: int = 2
    no_progress_block_after: int = 5


@dataclass(frozen=True)
class ToolCallSignature:
    tool_name: str
    args_hash: str

    @classmethod
    def from_call(cls, tool_name: str, args: Mapping[str, Any] | None) -> ToolCallSignature:
        canonical = _canonical_tool_args(_coerce_args(args))
        return cls(tool_name=tool_name, args_hash=_sha256(canonical))


@dataclass(frozen=True)
class GuardrailDecision:
    action: str = "allow"
    code: str = "allow"
    message: str = ""
    tool_name: str = ""
    count: int = 0

    @property
    def allows_execution(self) -> bool:
        return self.action in {"allow", "warn"}

    @property
    def should_halt(self) -> bool:
        return self.action in {"block", "halt"}


def _canonical_tool_args(args: Mapping[str, Any]) -> str:
    return json.dumps(args, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _coerce_args(args: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return args if isinstance(args, Mapping) else {}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def classify_tool_failure(tool_name: str, result: str | None) -> tuple[bool, str]:
    """Return (failed, suffix_hint) inferred from serialized tool output."""
    if result is None:
        return False, ""
    if tool_name in {"run_shell", "terminal"}:
        data = _safe_json_loads(result)
        if isinstance(data, dict):
            if data.get("error"):
                return True, " [error]"
            exit_code = data.get("exit_code")
            if exit_code is not None and exit_code != 0:
                return True, f" [exit {exit_code}]"
        return False, ""

    if tool_name.startswith("git_"):
        data = _safe_json_loads(result)
        if isinstance(data, dict):
            if data.get("error"):
                return True, " [error]"
            exit_code = data.get("exit_code")
            if exit_code is not None and exit_code != 0:
                return True, f" [exit {exit_code}]"
        return False, ""

    data = _safe_json_loads(result)
    if isinstance(data, dict):
        if data.get("success") is False:
            return True, " [error]"
        if data.get("error"):
            return True, " [error]"

    lower = result[:500].lower()
    if '"error"' in lower or '"failed"' in lower or result.startswith("Error"):
        return True, " [error]"
    return False, ""


def _result_hash(result: str | None) -> str:
    parsed = _safe_json_loads(result or "")
    if parsed is not None:
        try:
            canonical = json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        except TypeError:
            canonical = str(parsed)
    else:
        canonical = result or ""
    return _sha256(canonical)


class ToolCallGuardrailController:
    """Per-turn controller for repeated failed or non-progressing tool calls."""

    def __init__(self, config: GuardrailConfig | None = None):
        self.config = config or GuardrailConfig()
        self._lock = threading.RLock()
        self.reset_for_turn()

    def reset_for_turn(self) -> None:
        with self._lock:
            self._exact_failure_counts: dict[ToolCallSignature, int] = {}
            self._same_tool_failure_counts: dict[str, int] = {}
            self._no_progress: dict[ToolCallSignature, tuple[str, int]] = {}
            self._halt_decision: GuardrailDecision | None = None

    @property
    def halt_decision(self) -> GuardrailDecision | None:
        with self._lock:
            return self._halt_decision

    def set_halt_decision(self, decision: GuardrailDecision) -> None:
        """Record a halt/block decision from tool execution (thread-safe)."""
        with self._lock:
            if self._halt_decision is None:
                self._halt_decision = decision

    def before_call(self, tool_name: str, args: Mapping[str, Any] | None) -> GuardrailDecision:
        with self._lock:
            return self._before_call_locked(tool_name, args)

    def _before_call_locked(
        self, tool_name: str, args: Mapping[str, Any] | None
    ) -> GuardrailDecision:
        signature = ToolCallSignature.from_call(tool_name, args)
        if not self.config.hard_stop_enabled:
            return GuardrailDecision(tool_name=tool_name)

        exact_count = self._exact_failure_counts.get(signature, 0)
        if exact_count >= self.config.exact_failure_block_after:
            decision = GuardrailDecision(
                action="block",
                code="repeated_exact_failure_block",
                message=(
                    f"Blocked {tool_name}: same call failed {exact_count} times "
                    "with identical arguments. Change strategy."
                ),
                tool_name=tool_name,
                count=exact_count,
            )
            self._halt_decision = decision
            return decision

        if self._is_idempotent(tool_name):
            record = self._no_progress.get(signature)
            if record is not None:
                _rh, repeat_count = record
                if repeat_count >= self.config.no_progress_block_after:
                    decision = GuardrailDecision(
                        action="block",
                        code="idempotent_no_progress_block",
                        message=(
                            f"Blocked {tool_name}: returned same result {repeat_count} "
                            "times. Use the result already provided."
                        ),
                        tool_name=tool_name,
                        count=repeat_count,
                    )
                    self._halt_decision = decision
                    return decision

        return GuardrailDecision(tool_name=tool_name)

    def after_call(
        self,
        tool_name: str,
        args: Mapping[str, Any] | None,
        result: str | None,
        *,
        failed: bool | None = None,
    ) -> GuardrailDecision:
        with self._lock:
            return self._after_call_locked(tool_name, args, result, failed=failed)

    def _after_call_locked(
        self,
        tool_name: str,
        args: Mapping[str, Any] | None,
        result: str | None,
        *,
        failed: bool | None = None,
    ) -> GuardrailDecision:
        args = _coerce_args(args)
        signature = ToolCallSignature.from_call(tool_name, args)
        if failed is None:
            failed, _ = classify_tool_failure(tool_name, result)

        if failed:
            exact_count = self._exact_failure_counts.get(signature, 0) + 1
            self._exact_failure_counts[signature] = exact_count
            self._no_progress.pop(signature, None)

            same_count = self._same_tool_failure_counts.get(tool_name, 0) + 1
            self._same_tool_failure_counts[tool_name] = same_count

            if self.config.hard_stop_enabled and same_count >= self.config.same_tool_failure_halt_after:
                decision = GuardrailDecision(
                    action="halt",
                    code="same_tool_failure_halt",
                    message=(
                        f"Stopped {tool_name}: failed {same_count} times this turn. "
                        "Choose a different approach."
                    ),
                    tool_name=tool_name,
                    count=same_count,
                )
                self._halt_decision = decision
                return decision

            if self.config.warnings_enabled and exact_count >= self.config.exact_failure_warn_after:
                return GuardrailDecision(
                    action="warn",
                    code="repeated_exact_failure_warning",
                    message=f"{tool_name} failed {exact_count} times with identical args.",
                    tool_name=tool_name,
                    count=exact_count,
                )

            if self.config.warnings_enabled and same_count >= self.config.same_tool_failure_warn_after:
                return GuardrailDecision(
                    action="warn",
                    code="same_tool_failure_warning",
                    message=f"{tool_name} failed {same_count} times this turn.",
                    tool_name=tool_name,
                    count=same_count,
                )

            return GuardrailDecision(tool_name=tool_name, count=exact_count)

        self._exact_failure_counts.pop(signature, None)
        self._same_tool_failure_counts.pop(tool_name, None)

        if not self._is_idempotent(tool_name):
            self._no_progress.pop(signature, None)
            return GuardrailDecision(tool_name=tool_name)

        rh = _result_hash(result)
        previous = self._no_progress.get(signature)
        repeat_count = 1
        if previous is not None and previous[0] == rh:
            repeat_count = previous[1] + 1
        self._no_progress[signature] = (rh, repeat_count)

        if self.config.warnings_enabled and repeat_count >= self.config.no_progress_warn_after:
            return GuardrailDecision(
                action="warn",
                code="idempotent_no_progress_warning",
                message=f"{tool_name} returned the same result {repeat_count} times.",
                tool_name=tool_name,
                count=repeat_count,
            )

        return GuardrailDecision(tool_name=tool_name, count=repeat_count)

    def _is_idempotent(self, tool_name: str) -> bool:
        if tool_name in MUTATING_TOOLS:
            return False
        return tool_name in IDEMPOTENT_TOOLS


def guardrail_metadata(decision: GuardrailDecision) -> dict[str, Any]:
    """Structured guardrail payload for tool result envelopes."""
    payload: dict[str, Any] = {
        "action": decision.action,
        "code": decision.code,
        "count": decision.count,
        "message": decision.message,
    }
    if decision.tool_name:
        payload["tool_name"] = decision.tool_name
    return payload


def synthetic_result(decision: GuardrailDecision) -> str:
    """Build a synthetic tool result JSON for blocked calls."""
    return json.dumps({
        "error": decision.message,
        "guardrail": guardrail_metadata(decision),
    }, ensure_ascii=False)


def append_guidance(result: str, decision: GuardrailDecision) -> str:
    """Merge guardrail guidance into a tool result without breaking JSON envelopes."""
    if decision.action not in {"warn", "block", "halt"} or not decision.message:
        return result

    parsed = _safe_json_loads(result or "")
    if isinstance(parsed, dict):
        payload = dict(parsed)
        payload["guardrail"] = guardrail_metadata(decision)
        if decision.action in {"block", "halt"}:
            payload.setdefault("error", decision.message)
        return json.dumps(payload, ensure_ascii=False, default=str)

    label = "Tool loop hard stop" if decision.action in {"block", "halt"} else "Tool loop warning"
    return (result or "") + f"\n\n[{label}: {decision.code}; count={decision.count}; {decision.message}]"
