"""Tool-call loop detection and classification.

Detects pathological tool-call patterns that indicate the agent is stuck:
exact failure loops, repeated same-tool failures, no-progress sequences,
and idempotent-only loops. Provides warnings and optional hard-stops so the
agent can self-correct before burning tokens.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Deque, FrozenSet, Optional, Tuple


# ── Tool classification sets ──

IDEMPOTENT_TOOL_NAMES: FrozenSet[str] = frozenset({
    "read_file",
    "search_files",
    "search_codebase",
    "grep",
    "glob",
    "list_directory",
    "web_search",
    "web_fetch",
    "browser_snapshot",
    "browser_navigate",
    "browser_get_console_messages",
    "browser_network_requests",
    "get_tool_info",
    "get_domains_for_tool",
    "get_all_tools",
    "get_recommended_tools",
    "knowledge_search",
    "memory_query",
    "data_query",
    "project_todos",
    "session_todos",
    "memo",
    "habits",
    "reminder",
    "skill_view",
    "skills_list",
    "multimodal_analyze",
    "multimodal_describe",
    "download_tools",
    "experience_selector",
})

MUTATING_TOOL_NAMES: FrozenSet[str] = frozenset({
    "terminal",
    "terminal_run",
    "terminal_sandbox",
    "write_file",
    "patch",
    "delete_file",
    "create_file",
    "move_file",
    "rename_file",
    "browser_click",
    "browser_type",
    "browser_press_key",
    "browser_upload",
    "browser_form_submit",
    "browser_screenshot",
    "execute_code",
    "run_workflow",
    "delegate_task",
    "delegate_run",
    "git_commit",
    "git_push",
    "git_checkout",
    "git_merge",
    "git_rebase",
    "git_tag",
    "create_branch",
    "create_tag",
    "add_experience",
    "update_experience",
    "delete_experience",
    "record_habit",
    "project_todos_update",
    "session_todos_update",
    "expense_log",
    "add_memo",
    "update_memo",
    "delete_memo",
    "network_route_verify",
    "add_knowledge",
    "consistency_summary",
})


# ── Classification helper ──


def classify_tool(tool_name: str) -> str:
    """Classify a tool as ``idempotent``, ``mutating``, or ``unknown``.

    Classification is based on the static frozensets. Unknown tools are
    treated as neither safe nor dangerous — the caller decides policy.
    """
    if tool_name in IDEMPOTENT_TOOL_NAMES:
        return "idempotent"
    if tool_name in MUTATING_TOOL_NAMES:
        return "mutating"
    return "unknown"


# ── Data structures ──


@dataclass(frozen=True)
class ToolCallGuardrailConfig:
    """Tunable thresholds for tool-call guardrails.

    All thresholds are inclusive: when a counter reaches the configured
    value the corresponding decision fires.  Defaults are chosen to be
    conservative enough to catch real loops without penalising normal
    retry bursts.
    """

    warnings_enabled: bool = True
    hard_stop_enabled: bool = False

    exact_failure_warn_after: int = 2
    exact_failure_block_after: int = 5

    same_tool_failure_warn_after: int = 3
    same_tool_failure_halt_after: int = 8

    no_progress_warn_after: int = 2
    no_progress_block_after: int = 5

    idempotent_tools: FrozenSet[str] = field(
        default_factory=lambda: IDEMPOTENT_TOOL_NAMES,
    )
    mutating_tools: FrozenSet[str] = field(
        default_factory=lambda: MUTATING_TOOL_NAMES,
    )


@dataclass
class GuardrailDecision:
    """Outcome of a :class:`ToolCallGuardrail.check` call."""

    should_warn: bool = False
    should_hard_stop: bool = False
    warning_message: Optional[str] = None
    halt_message: Optional[str] = None
    reason: str = "ok"


# ── Internal observation record ──


@dataclass
class _Observation:
    tool_name: str
    result_ok: bool
    result_summary: str = ""


# ── Guardrail ──


class ToolCallGuardrail:
    """Track per-turn tool-call observations and detect loop patterns.

    Usage::

        guardrail = ToolCallGuardrail()
        guardrail.observe("read_file", True)
        decision = guardrail.check()
        if decision.should_hard_stop:
            ...

    Observations are stored in a bounded deque (see ``max_history``) so
    that very long sessions do not grow unboundedly.
    """

    def __init__(
        self,
        config: Optional[ToolCallGuardrailConfig] = None,
        max_history: int = 100,
    ) -> None:
        self._config = config or ToolCallGuardrailConfig()
        self._max_history = max_history
        self._history: Deque[_Observation] = deque(maxlen=max_history)

    # ── Public API ──

    @property
    def config(self) -> ToolCallGuardrailConfig:
        return self._config

    @property
    def history(self) -> Tuple[_Observation, ...]:
        return tuple(self._history)

    def observe(
        self,
        tool_name: str,
        result_ok: bool,
        result_summary: Optional[str] = None,
    ) -> None:
        """Record a single tool-call observation."""
        self._history.append(
            _Observation(
                tool_name=tool_name,
                result_ok=result_ok,
                result_summary=result_summary or "",
            ),
        )

    def reset(self) -> None:
        """Clear all observations."""
        self._history.clear()

    def check(self) -> GuardrailDecision:
        """Analyse the current state and return a guardrail decision.

        Detection order follows severity: hard stops (block/halt) are
        evaluated first, then warnings.  Only the most severe finding is
        reported per call so that the agent gets a single clear signal.
        """
        cfg = self._config

        # 1. Exact failure loop (highest severity).
        decision = self._check_exact_failure(cfg)
        if decision is not None:
            return decision

        # 2. Same-tool repeated failure.
        decision = self._check_same_tool_failure(cfg)
        if decision is not None:
            return decision

        # 3. No-progress sequence.
        decision = self._check_no_progress(cfg)
        if decision is not None:
            return decision

        # 4. Idempotent-only loop.
        decision = self._check_idempotent_only(cfg)
        if decision is not None:
            return decision

        return GuardrailDecision(reason="ok")

    # ── Detectors ──

    def _check_exact_failure(
        self,
        cfg: ToolCallGuardrailConfig,
    ) -> Optional[GuardrailDecision]:
        """Detect the same tool failing repeatedly with the *same* error."""
        # Walk history and count consecutive (tool, summary) matches
        # on failed calls.
        counts: Counter[Tuple[str, str]] = Counter()
        for obs in self._history:
            if obs.result_ok:
                continue
            key = (obs.tool_name, obs.result_summary)
            counts[key] += 1

        if not counts:
            return None

        (tool_name, summary), count = counts.most_common(1)[0]

        if cfg.hard_stop_enabled and count >= cfg.exact_failure_block_after:
            return GuardrailDecision(
                should_warn=False,
                should_hard_stop=True,
                halt_message=(
                    f"Tool '{tool_name}' failed {count} times with the "
                    f"same error — halting to prevent a loop. "
                    f"Error: {summary[:200]}"
                ),
                reason="exact_failure_block",
            )

        if cfg.warnings_enabled and count >= cfg.exact_failure_warn_after:
            return GuardrailDecision(
                should_warn=True,
                should_hard_stop=False,
                warning_message=(
                    f"Tool '{tool_name}' failed {count} times with the "
                    f"same error — consider a different approach. "
                    f"Error: {summary[:200]}"
                ),
                reason="exact_failure_warn",
            )

        return None

    def _check_same_tool_failure(
        self,
        cfg: ToolCallGuardrailConfig,
    ) -> Optional[GuardrailDecision]:
        """Detect the same tool failing multiple times (any error)."""
        counts: Counter[str] = Counter()
        for obs in self._history:
            if not obs.result_ok:
                counts[obs.tool_name] += 1

        if not counts:
            return None

        tool_name, count = counts.most_common(1)[0]

        if cfg.hard_stop_enabled and count >= cfg.same_tool_failure_halt_after:
            return GuardrailDecision(
                should_warn=False,
                should_hard_stop=True,
                halt_message=(
                    f"Tool '{tool_name}' has failed {count} times with "
                    f"different errors — halting to prevent a loop."
                ),
                reason="same_tool_failure_halt",
            )

        if cfg.warnings_enabled and count >= cfg.same_tool_failure_warn_after:
            return GuardrailDecision(
                should_warn=True,
                should_hard_stop=False,
                warning_message=(
                    f"Tool '{tool_name}' has failed {count} times — "
                    f"consider switching tools or revising the approach."
                ),
                reason="same_tool_failure_warn",
            )

        return None

    def _check_no_progress(
        self,
        cfg: ToolCallGuardrailConfig,
    ) -> Optional[GuardrailDecision]:
        """Detect consecutive mutating calls without meaningful progress.

        A "no progress" run is a trailing window of mutating tool calls
        that never succeeded and never allowed an idempotent read between
        them.  This signals the agent is thrashing (e.g. repeatedly
        ``patch``ing the same file without checking the result).
        """
        idem = cfg.idempotent_tools
        mut = cfg.mutating_tools

        # Find the trailing contiguous block of mutating calls since the
        # last successful idempotent call (or start of history).
        mutating_since_last_progress = 0
        for obs in reversed(self._history):
            if obs.tool_name in idem and obs.result_ok:
                break
            if obs.tool_name in mut:
                mutating_since_last_progress += 1
            else:
                break

        if mutating_since_last_progress == 0:
            return None

        if cfg.hard_stop_enabled and mutating_since_last_progress >= cfg.no_progress_block_after:
            return GuardrailDecision(
                should_warn=False,
                should_hard_stop=True,
                halt_message=(
                    f"{mutating_since_last_progress} consecutive mutating "
                    f"tool calls without any successful read — halting to "
                    f"prevent destructive thrashing."
                ),
                reason="no_progress_block",
            )

        if cfg.warnings_enabled and mutating_since_last_progress >= cfg.no_progress_warn_after:
            return GuardrailDecision(
                should_warn=True,
                should_hard_stop=False,
                warning_message=(
                    f"{mutating_since_last_progress} consecutive mutating "
                    f"tool calls without any successful read — consider "
                    f"verifying state with a read tool before proceeding."
                ),
                reason="no_progress_warn",
            )

        return None

    def _check_idempotent_only(
        self,
        cfg: ToolCallGuardrailConfig,
    ) -> Optional[GuardrailDecision]:
        """Detect the agent stuck in read-only tools without mutating action.

        This catches the pattern where an agent keeps reading files or
        searching the web but never actually *does* anything.  We look
        for a long trailing run of successful idempotent calls with no
        mutating calls interspersed.
        """
        idem = cfg.idempotent_tools
        mut = cfg.mutating_tools

        trailing_idem_ok = 0
        for obs in reversed(self._history):
            if obs.tool_name in mut:
                break
            if obs.tool_name in idem and obs.result_ok:
                trailing_idem_ok += 1
            elif obs.tool_name in idem:
                # Successful or not, an idempotent tool resets the run
                # when it's not purely success-only — keep counting the
                # "read-only" streak.
                trailing_idem_ok += 1
            else:
                break

        # Reuse no-progress thresholds for idempotent-only detection
        # since they are conceptually similar "stuck" patterns.
        if trailing_idem_ok == 0:
            return None

        if cfg.warnings_enabled and trailing_idem_ok >= cfg.no_progress_warn_after:
            return GuardrailDecision(
                should_warn=True,
                should_hard_stop=False,
                warning_message=(
                    f"{trailing_idem_ok} consecutive read-only tool calls "
                    f"with no mutating action — consider making a change "
                    f"or asking the user for clarification."
                ),
                reason="idempotent_only_warn",
            )

        return None


# ── Module-level exports ──


__all__ = [
    "IDEMPOTENT_TOOL_NAMES",
    "MUTATING_TOOL_NAMES",
    "ToolCallGuardrailConfig",
    "ToolCallGuardrail",
    "GuardrailDecision",
    "classify_tool",
]
