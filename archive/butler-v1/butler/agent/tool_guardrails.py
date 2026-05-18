"""Pure tool-call loop guardrail primitives (two-phase: before_call + after_call).

Actions: ``allow``, ``warn``, ``block``, ``halt``. The controller tracks per-turn
state only; callers decide how to surface warnings, synthetic blocked results,
or halts.

Adapted from Hermes Agent patterns; Butler-specific tool names only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

IDEMPOTENT_TOOLS = frozenset(
    {
        "read_file",
        "search_code",
        "list_directory",
        "git_status",
        "git_diff",
        "git_log",
        "git_branch",
    }
)

MUTATING_TOOLS = frozenset(
    {
        "run_shell",
        "write_file",
        "edit_file",
        "patch",
        "git_add",
        "git_commit",
        "delegate_to_dev_agent",
        "delegate_to_content_agent",
        "delegate_to_review_agent",
    }
)


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
    action: str = "allow"  # allow | warn | block | halt
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
    return json.dumps(
        args,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


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

    if tool_name == "run_shell":
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
            canonical = json.dumps(
                parsed,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
        except TypeError:
            canonical = str(parsed)
    else:
        canonical = result or ""
    return _sha256(canonical)


class ToolCallGuardrailController:
    """Per-turn controller for repeated failed or non-progressing tool calls."""

    def __init__(self, config: GuardrailConfig | None = None):
        self.config = config or GuardrailConfig()
        self.reset_for_turn()

    def reset_for_turn(self) -> None:
        self._exact_failure_counts: dict[ToolCallSignature, int] = {}
        self._same_tool_failure_counts: dict[str, int] = {}
        self._no_progress: dict[ToolCallSignature, tuple[str, int]] = {}
        self._halt_decision: GuardrailDecision | None = None

    @property
    def halt_decision(self) -> GuardrailDecision | None:
        return self._halt_decision

    def before_call(self, tool_name: str, args: Mapping[str, Any] | None) -> GuardrailDecision:
        signature = ToolCallSignature.from_call(tool_name, args)
        if not self.config.hard_stop_enabled:
            return GuardrailDecision(tool_name=tool_name)

        exact_count = self._exact_failure_counts.get(signature, 0)
        if exact_count >= self.config.exact_failure_block_after:
            decision = GuardrailDecision(
                action="block",
                code="repeated_exact_failure_block",
                message=(
                    f"Blocked {tool_name}: the same tool call failed {exact_count} "
                    "times with identical arguments. Stop retrying it unchanged; "
                    "change strategy or explain the blocker."
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
                            f"Blocked {tool_name}: this read-only call returned the same "
                            f"result {repeat_count} times. Stop repeating it unchanged; "
                            "use the result already provided or try a different query."
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
                        f"Stopped {tool_name}: it failed {same_count} times this turn. "
                        "Stop retrying the same failing tool path and choose a different approach."
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
                    message=(
                        f"{tool_name} has failed {exact_count} times with identical arguments. "
                        "This looks like a loop; inspect the error and change strategy "
                        "instead of retrying it unchanged."
                    ),
                    tool_name=tool_name,
                    count=exact_count,
                )

            if self.config.warnings_enabled and same_count >= self.config.same_tool_failure_warn_after:
                return GuardrailDecision(
                    action="warn",
                    code="same_tool_failure_warning",
                    message=(
                        f"{tool_name} has failed {same_count} times this turn. "
                        "This looks like a loop; change approach before retrying."
                    ),
                    tool_name=tool_name,
                    count=same_count,
                )

            return GuardrailDecision(tool_name=tool_name, count=exact_count)

        self._exact_failure_counts.pop(signature, None)
        self._same_tool_failure_counts.pop(tool_name, None)

        if not self._is_idempotent(tool_name):
            self._no_progress.pop(signature, None)
            return GuardrailDecision(tool_name=tool_name)

        result_hash = _result_hash(result)
        previous = self._no_progress.get(signature)
        repeat_count = 1
        if previous is not None and previous[0] == result_hash:
            repeat_count = previous[1] + 1
        self._no_progress[signature] = (result_hash, repeat_count)

        if self.config.warnings_enabled and repeat_count >= self.config.no_progress_warn_after:
            return GuardrailDecision(
                action="warn",
                code="idempotent_no_progress_warning",
                message=(
                    f"{tool_name} returned the same result {repeat_count} times. "
                    "Use the result already provided or change the query instead of "
                    "repeating it unchanged."
                ),
                tool_name=tool_name,
                count=repeat_count,
            )

        return GuardrailDecision(tool_name=tool_name, count=repeat_count)

    def _is_idempotent(self, tool_name: str) -> bool:
        if tool_name in MUTATING_TOOLS:
            return False
        if tool_name in IDEMPOTENT_TOOLS:
            return True
        return False


def synthetic_result(decision: GuardrailDecision) -> str:
    """Build a synthetic tool result JSON for blocked calls."""
    return json.dumps(
        {
            "error": decision.message,
            "guardrail": {
                "action": decision.action,
                "code": decision.code,
                "message": decision.message,
                "tool_name": decision.tool_name,
                "count": decision.count,
            },
        },
        ensure_ascii=False,
    )


def append_guidance(result: str, decision: GuardrailDecision) -> str:
    """Append warning or halt-style guidance to a tool result string."""
    if decision.action not in {"warn", "block", "halt"} or not decision.message:
        return result
    label = (
        "Tool loop hard stop"
        if decision.action in {"block", "halt"}
        else "Tool loop warning"
    )
    suffix = f"\n\n[{label}: {decision.code}; count={decision.count}; {decision.message}]"
    return (result or "") + suffix
