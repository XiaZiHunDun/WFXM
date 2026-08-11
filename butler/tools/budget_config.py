"""Immutable budget configuration for multi-layer tool result persistence.

This module provides a frozen configuration object that controls how
much tool output is retained inline vs. persisted to disk per result
and per turn.  The companion :class:`TurnBudgetTracker` is a lightweight
runtime helper that accumulates the size of tool results produced in a
single agent turn and reports whether the aggregate budget has been
exceeded so that downstream persistence logic can flush / summarize /
drop data accordingly.

Design principles:

* Immutability — :class:`BudgetConfig` is a frozen dataclass so that
  budget decisions cannot be mutated mid-turn (which would be unsafe
  when the config is shared across threads / tasks).
* Proportional scaling — every numeric threshold can be rescaled to
  the target model context window via :meth:`BudgetConfig.scale_to_context`
  so the same code base can serve 8 k BPE models and 200 k BPE models
  without hand-tuning.
* Pin protection — certain tools (``read_file``, etc.) must *never* be
  subjected to a result-size cap, because capping them would defeat
  the whole purpose of reading a file and lead to silent data loss or
  ``persist → read → persist`` feedback loops.  See ``PINNED_THRESHOLDS``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional


# ── constants ────────────────────────────────────────────────────

DEFAULT_RESULT_SIZE_CHARS: int = 100_000
"""Default per-result size threshold in characters."""

DEFAULT_TURN_BUDGET_CHARS: int = 200_000
"""Default aggregate per-turn budget in characters."""

DEFAULT_PREVIEW_SIZE_CHARS: int = 1_500
"""Default size of the inline snippet kept after persistence."""

_CHARS_PER_TOKEN: int = 4
"""Rough token → character conversion factor used for budget scaling."""

_PER_RESULT_WINDOW_FRACTION: float = 0.15
"""Fraction of the model context window reserved for a single result."""

_PER_TURN_WINDOW_FRACTION: float = 0.30
"""Fraction of the model context window reserved for the whole turn."""

_MIN_RESULT_SIZE_CHARS: int = 8_000
"""Floor applied when scaling down so tiny models still get a usable budget."""


# Tools whose thresholds MUST NEVER be overridden.
# Mapping is ``tool_name → threshold_in_chars``.  ``math.inf`` means
# "never cap the result" which is the correct behaviour for tools like
# ``read_file`` — capping a read would silently truncate source code
# viewed by the model, producing incorrect downstream decisions.
PINNED_THRESHOLDS: Dict[str, float] = {
    "read_file": math.inf,
    "read_multiple_files": math.inf,
    "glob": math.inf,
    "grep": math.inf,
    "list_dir": math.inf,
    "list_project_files": math.inf,
    "web_fetch": math.inf,
    "web_search": math.inf,
}


# ── helpers ───────────────────────────────────────────────────────


def _scale_result_size(context_window_tokens: int) -> int:
    """Scale the per-result budget proportionally to *context_window_tokens*."""

    context_chars = context_window_tokens * _CHARS_PER_TOKEN
    scaled = math.ceil(context_chars * _PER_RESULT_WINDOW_FRACTION)
    return max(_MIN_RESULT_SIZE_CHARS, scaled)


def _scale_turn_budget(context_window_tokens: int) -> int:
    """Scale the per-turn budget proportionally to *context_window_tokens*."""

    context_chars = context_window_tokens * _CHARS_PER_TOKEN
    scaled = math.ceil(context_chars * _PER_TURN_WINDOW_FRACTION)
    return max(_MIN_RESULT_SIZE_CHARS * 2, scaled)


# ── BudgetConfig ─────────────────────────────────────────────────


@dataclass(frozen=True)
class BudgetConfig:
    """Immutable configuration governing tool-result persistence budgets.

    Attributes:
        default_result_size:
            Default cap (chars) applied to any tool result that has no
            more specific override.  ``math.inf`` disables the cap.
        turn_budget:
            Aggregate per-turn cap (chars) across *all* tool results
            produced in a single agent step.  When this is exceeded the
            :class:`TurnBudgetTracker` reports ``exceeded() == True`` so
            that callers can flush / summarize / drop data.
        preview_size:
            Number of characters retained inline after a tool result has
            been persisted to disk (``=`` the size of the snippet the
            model sees in the follow-up message).
        tool_overrides:
            Tool-specific overrides keyed by tool name.  These take
            precedence over the registry's ``max_result_size`` value
            (but *not* over the :data:`PINNED_THRESHOLDS`).
    """

    default_result_size: int = DEFAULT_RESULT_SIZE_CHARS
    turn_budget: int = DEFAULT_TURN_BUDGET_CHARS
    preview_size: int = DEFAULT_PREVIEW_SIZE_CHARS
    tool_overrides: Dict[str, int] = field(default_factory=dict)

    # ── resolution ────────────────────────────────────────────────

    def resolve_threshold(
        self,
        tool_name: str,
        registry: Optional[Mapping[str, int]] = None,
    ) -> float:
        """Return the effective per-result threshold for *tool_name*.

        Resolution priority (highest → lowest):

        1. :data:`PINNED_THRESHOLDS` — pinned tools always return the
           pinned value (typically ``math.inf``) regardless of any
           caller-supplied override.
        2. ``tool_overrides`` set on this config instance.
        3. ``registry[tool_name]`` — tool-specific threshold registered
           externally (e.g. via the :class:`ToolRegistry`).
        4. ``default_result_size`` — the config-wide default.

        :param tool_name:
            Exact tool identifier as registered with the tool system.
        :param registry:
            Optional mapping ``{tool_name → threshold}``.  If supplied
            and *tool_name* is missing from both the pinned set and the
            local overrides, this mapping is consulted as the third
            source of truth before falling back to the default.
        :returns:
            The effective threshold in chars.  May be ``math.inf`` when
            the tool is pinned or when an override was explicitly set
            to infinity.  The return type is ``float`` because it may
            be ``math.inf``; consumers that expect a finite integer
            should check ``math.isfinite(value)`` first.
        """

        if tool_name in PINNED_THRESHOLDS:
            return PINNED_THRESHOLDS[tool_name]
        override = self.tool_overrides.get(tool_name)
        if override is not None:
            return float(override)
        if registry is not None:
            registry_value = registry.get(tool_name)
            if registry_value is not None:
                return float(registry_value)
        return float(self.default_result_size)

    # ── scaling ───────────────────────────────────────────────────

    def scale_to_context(self, context_window_tokens: int) -> "BudgetConfig":
        """Return a new config with thresholds rescaled to *context_window_tokens*.

        The scaling preserves the relative proportions documented in the
        module-level constants but never produces a value below
        ``_MIN_RESULT_SIZE_CHARS`` so that very small models still get
        a usable budget.

        :param context_window_tokens:
            Model context window expressed in tokens (BPE).
        :returns:
            A new :class:`BudgetConfig` instance with rescaled
            ``default_result_size`` and ``turn_budget``.  ``preview_size``
            and ``tool_overrides`` are preserved verbatim — they encode
            user intent, not window size.
        """

        scaled_result = _scale_result_size(context_window_tokens)
        scaled_turn = _scale_turn_budget(context_window_tokens)
        return BudgetConfig(
            default_result_size=scaled_result,
            turn_budget=scaled_turn,
            preview_size=self.preview_size,
            tool_overrides=dict(self.tool_overrides),
        )

    # ── construction helpers ──────────────────────────────────────

    def with_overrides(self, overrides: Mapping[str, int]) -> "BudgetConfig":
        """Return a new config merging *overrides* into ``tool_overrides``.

        Existing entries are preserved; entries in *overrides* take
        precedence when keys collide.  The original instance is never
        mutated (frozen dataclass contract).
        """

        merged: Dict[str, int] = dict(self.tool_overrides)
        for key, value in overrides.items():
            merged[key] = value
        return BudgetConfig(
            default_result_size=self.default_result_size,
            turn_budget=self.turn_budget,
            preview_size=self.preview_size,
            tool_overrides=merged,
        )


# ── default singleton ─────────────────────────────────────────────

DEFAULT_BUDGET: BudgetConfig = BudgetConfig()
"""Module-wide default :class:`BudgetConfig` instance.

Consumers that do not need custom thresholds can import this singleton
directly:

.. code-block:: python

    from butler.tools.budget_config import DEFAULT_BUDGET
    threshold = DEFAULT_BUDGET.resolve_threshold("read_file")
"""


# ── TurnBudgetTracker ─────────────────────────────────────────────


class TurnBudgetTracker:
    """Accumulates tool-result sizes for a single agent turn.

    Usage::

        tracker = TurnBudgetTracker(budget)
        for result in tool_results:
            tracker.record_result(result.tool_name, len(result.content))
            if tracker.exceeded():
                flush_persistence_buffers()
                break

        remaining = tracker.remaining()
        if tracker.exceeded():
            # trigger summarization / fallback persistence
            ...

    The tracker is *not* thread-safe — budget accounting is an
    intrinsically per-turn, single-threaded concern.
    """

    __slots__ = ("_budget", "_used", "_tool_totals")

    def __init__(self, budget: BudgetConfig = DEFAULT_BUDGET) -> None:
        self._budget = budget
        self._used: int = 0
        self._tool_totals: Dict[str, int] = {}

    # ── mutation ──────────────────────────────────────────────────

    def record_result(self, tool_name: str, char_count: int) -> None:
        """Record a single tool result of *char_count* chars.

        :param tool_name:
            Tool identifier (used for per-tool accounting breakdown).
        :param char_count:
            Size of the result in characters.  Negative values are
            treated as zero — callers may safely pass ``len(content)``
            for any string-like payload.
        """

        if char_count < 0:
            char_count = 0
        self._used += char_count
        self._tool_totals[tool_name] = self._tool_totals.get(tool_name, 0) + char_count

    def reset(self) -> None:
        """Reset all accumulators (start of a new turn)."""

        self._used = 0
        self._tool_totals.clear()

    # ── queries ───────────────────────────────────────────────────

    @property
    def used(self) -> int:
        """Total characters recorded so far this turn."""

        return self._used

    @property
    def tool_totals(self) -> Dict[str, int]:
        """Per-tool character totals (defensive copy)."""

        return dict(self._tool_totals)

    def remaining(self) -> int:
        """Characters left before the aggregate budget is exhausted.

        If the budget has already been overrun the returned value is
        clamped to ``0`` so callers can safely use it as a capacity
        hint without additional guard checks.
        """

        remaining = self._budget.turn_budget - self._used
        return remaining if remaining > 0 else 0

    def exceeded(self) -> bool:
        """Return ``True`` when the turn budget has been exhausted."""

        return self._used >= self._budget.turn_budget

    def tool_count(self) -> int:
        """Number of distinct tool names recorded this turn."""

        return len(self._tool_totals)


# ── tests (``python -m butler.tools.budget_config``) ─────────────

if __name__ == "__main__":  # pragma: no cover - manual smoke tests
    def _assert(condition: bool, message: str) -> None:
        if not condition:
            raise AssertionError(message)

    config = BudgetConfig()

    # ── 1. Priority resolution ──────────────────────────────────
    # Pinned tool wins over everything
    pinned_threshold = config.resolve_threshold("read_file")
    _assert(math.isinf(pinned_threshold), "read_file must be pinned to inf")

    # Tool override wins over registry
    override_cfg = config.with_overrides({"my_tool": 42})
    registry_map = {"my_tool": 9999, "another_tool": 8888}
    _assert(
        override_cfg.resolve_threshold("my_tool", registry_map) == 42,
        "tool_overrides must take precedence over registry",
    )
    # Registry consulted when no override
    _assert(
        override_cfg.resolve_threshold("another_tool", registry_map) == 8888,
        "registry must be consulted when no override exists",
    )
    # Falls back to default when neither
    _assert(
        config.resolve_threshold("unknown_tool") == DEFAULT_RESULT_SIZE_CHARS,
        "must fall back to default_result_size",
    )

    # ── 2. Context window scaling ───────────────────────────────
    tiny_cfg = config.scale_to_context(4_000)
    _assert(tiny_cfg.default_result_size >= _MIN_RESULT_SIZE_CHARS,
            "scaled result must not drop below MIN_RESULT_SIZE_CHARS")
    _assert(tiny_cfg.turn_budget >= _MIN_RESULT_SIZE_CHARS * 2,
            "scaled turn budget must not drop below 2x MIN_RESULT_SIZE_CHARS")

    large_cfg = config.scale_to_context(200_000)
    _assert(
        large_cfg.default_result_size > config.default_result_size,
        "scaling to a larger window must increase result size",
    )
    _assert(
        large_cfg.turn_budget > config.turn_budget,
        "scaling to a larger window must increase turn budget",
    )
    _assert(
        large_cfg.preview_size == DEFAULT_PREVIEW_SIZE_CHARS,
        "preview_size must be preserved by scale_to_context",
    )

    # Proportional sanity check for a 200k context
    expected_result = max(
        _MIN_RESULT_SIZE_CHARS,
        math.ceil(200_000 * _CHARS_PER_TOKEN * _PER_RESULT_WINDOW_FRACTION),
    )
    _assert(
        large_cfg.default_result_size == expected_result,
        "200k scaling must match documented fraction",
    )

    # ── 3. Pin protection ────────────────────────────────────────
    # Override must NOT be able to override a pinned tool
    attacked_cfg = config.with_overrides({"read_file": 1000})
    _assert(
        math.isinf(attacked_cfg.resolve_threshold("read_file")),
        "pinned tools must be immune to tool_overrides",
    )
    attacked_cfg2 = config.with_overrides({"read_file": 1000})
    registry_pinned = {"read_file": 500}
    _assert(
        math.isinf(attacked_cfg2.resolve_threshold("read_file", registry_pinned)),
        "pinned tools must be immune to registry overrides",
    )

    # Glob/grep/web_fetch are also pinned
    for pinned_tool in ("glob", "grep", "web_fetch", "list_dir"):
        _assert(
            math.isinf(config.resolve_threshold(pinned_tool)),
            f"{pinned_tool} must be pinned",
        )

    # ── 4. Turn budget tracking ─────────────────────────────────
    tracker = TurnBudgetTracker(budget=BudgetConfig(turn_budget=1_000))
    _assert(tracker.used == 0, "initial used must be 0")
    _assert(tracker.remaining() == 1_000, "initial remaining must equal turn_budget")
    _assert(tracker.exceeded() is False, "must not be exceeded at start")
    _assert(tracker.tool_count() == 0, "tool_count must be 0 before any record")

    tracker.record_result("bash", 300)
    tracker.record_result("bash", 200)
    tracker.record_result("read_file", 400)
    _assert(tracker.used == 900, "used must sum recorded chars")
    _assert(tracker.tool_count() == 2, "must count distinct tools")
    _assert(tracker.remaining() == 100, "remaining must equal budget - used")
    _assert(tracker.exceeded() is False, "must not be exceeded below budget")

    tracker.record_result("bash", 200)  # pushes us over
    _assert(tracker.used == 1_100, "used must keep growing")
    _assert(tracker.remaining() == 0, "remaining must clamp to 0 after overrun")
    _assert(tracker.exceeded() is True, "must be exceeded once budget overrun")

    # Negative char counts are treated as zero
    tracker.record_result("bash", -50)
    _assert(tracker.used == 1_100, "negative char_count must be treated as zero")

    tool_totals = tracker.tool_totals
    _assert(tool_totals.get("bash") == 700, "per-tool bash total must be 700")
    _assert(tool_totals.get("read_file") == 400, "per-tool read_file total must be 400")

    # reset() wipes state
    tracker.reset()
    _assert(tracker.used == 0, "reset must zero used")
    _assert(tracker.remaining() == 1_000, "reset must restore full remaining")
    _assert(tracker.exceeded() is False, "reset must clear exceeded flag")
    _assert(tracker.tool_count() == 0, "reset must clear tool_totals")

    # with_overrides produces a new frozen instance
    merged = config.with_overrides({"custom_tool": 5_000})
    _assert(
        merged.resolve_threshold("custom_tool") == 5_000,
        "with_overrides must add a new threshold",
    )
    _assert(
        merged.resolve_threshold("read_file") == math.inf,
        "with_overrides must not affect pinned tools",
    )
    _assert(
        config.resolve_threshold("custom_tool") == DEFAULT_RESULT_SIZE_CHARS,
        "original config must remain unchanged (immutable)",
    )

    # DEFAULT_BUDGET singleton is usable directly
    _assert(
        DEFAULT_BUDGET.resolve_threshold("unknown") == DEFAULT_RESULT_SIZE_CHARS,
        "DEFAULT_BUDGET must behave like default config",
    )

    print("budget_config: all smoke tests passed ✓")
