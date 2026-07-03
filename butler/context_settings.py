"""Context stack settings: ``config.yaml`` ``context.*`` with env overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from butler.config import get_butler_settings
from butler.defaults.env_defaults import (
    CONTEXT_BLOCKING_BUFFER,
    CONTEXT_COMPACT_MAX_FAILURES,
    CONTEXT_COMPACT_RESERVE,
    CONTEXT_ERROR_BUFFER,
    CONTEXT_OUTPUT_RESERVE,
    CONTEXT_WARNING_BUFFER,
    INSTRUCTION_WALKUP_MAX_CHARS,
    INSTRUCTION_WALKUP_MAX_FILES,
    TOOL_PRUNE_CLEARABLE_CHARS,
    TOOL_PRUNE_DEFAULT_CHARS,
    TOOL_PRUNE_KEEP_RECENT,
    TOOL_PRUNE_PII_CHARS,
    TOOL_PRUNE_PIM_KEEP_RECENT,
    TOOL_PRUNE_PRESERVE_CHARS,
    TURN_BUDGET_DEFAULT,
    TURN_BUDGET_MAX_ITERATIONS,
    TURN_BUDGET_MIN_ITERATIONS,
)
from butler.env_parse import env_truthy, int_env

_TOOL_PRUNE_BACKWARD_MINIMUM = 20_000
_TOOL_PRUNE_BACKWARD_PROTECT = 40_000
_TURN_BUDGET_MAX_CONTINUATIONS = 3
_TURN_BUDGET_MIN_DELTA = 500


@dataclass
class ContextBudgetSettings:
    output_reserve: int = CONTEXT_OUTPUT_RESERVE
    compact_reserve: int = CONTEXT_COMPACT_RESERVE
    warning_buffer: int = CONTEXT_WARNING_BUFFER
    error_buffer: int = CONTEXT_ERROR_BUFFER
    blocking_buffer: int = CONTEXT_BLOCKING_BUFFER
    compact_max_failures: int = CONTEXT_COMPACT_MAX_FAILURES


@dataclass
class TurnBudgetSettings:
    enabled: bool = True
    default_tokens: int = TURN_BUDGET_DEFAULT
    min_iterations: int = TURN_BUDGET_MIN_ITERATIONS
    max_iterations: int = TURN_BUDGET_MAX_ITERATIONS
    max_continuations: int = _TURN_BUDGET_MAX_CONTINUATIONS
    min_delta: int = _TURN_BUDGET_MIN_DELTA


@dataclass
class ToolPruneSettings:
    keep_recent: int = TOOL_PRUNE_KEEP_RECENT
    pim_keep_recent: int = TOOL_PRUNE_PIM_KEEP_RECENT
    pii_chars: int = TOOL_PRUNE_PII_CHARS
    clearable_chars: int = TOOL_PRUNE_CLEARABLE_CHARS
    preserve_chars: int = TOOL_PRUNE_PRESERVE_CHARS
    default_chars: int = TOOL_PRUNE_DEFAULT_CHARS
    backward_enabled: bool = True
    backward_minimum: int = _TOOL_PRUNE_BACKWARD_MINIMUM
    backward_protect: int = _TOOL_PRUNE_BACKWARD_PROTECT


@dataclass
class InstructionWalkupSettings:
    enabled: bool = True
    max_chars: int = INSTRUCTION_WALKUP_MAX_CHARS
    max_files: int = INSTRUCTION_WALKUP_MAX_FILES


@dataclass
class ContextConfig:
    budget: ContextBudgetSettings = field(default_factory=ContextBudgetSettings)
    turn_budget: TurnBudgetSettings = field(default_factory=TurnBudgetSettings)
    tool_prune: ToolPruneSettings = field(default_factory=ToolPruneSettings)
    instruction_walkup: InstructionWalkupSettings = field(
        default_factory=InstructionWalkupSettings
    )
    yaml_configured: bool = False


def _load_yaml_context() -> dict[str, Any]:
    settings = get_butler_settings()
    from butler.context_settings_ops import load_yaml_context_section_safe

    return load_yaml_context_section_safe(settings.config_yaml_path)


def _nested_dict(raw: dict[str, Any], key: str) -> dict[str, Any]:
    child = raw.get(key)
    return child if isinstance(child, dict) else {}


def _int_from_raw(raw: dict[str, Any], key: str, default: int) -> int:
    if key not in raw:
        return default
    try:
        return int(raw[key])
    except (TypeError, ValueError):
        return default


def _bool_from_raw(raw: dict[str, Any], key: str, default: bool) -> bool:
    if key not in raw:
        return default
    return bool(raw[key])


def _merged_int(
    root: dict[str, Any],
    section: dict[str, Any],
    key: str,
    env_name: str,
    default: int,
    *,
    min: int = 0,
) -> int:
    if key in section:
        yaml_default = _int_from_raw(section, key, default)
    elif key in root:
        yaml_default = _int_from_raw(root, key, default)
    else:
        yaml_default = default
    return int_env(env_name, yaml_default, min=min)


def resolve_context_config() -> ContextConfig:
    """Merge ``config.yaml`` ``context.*`` with env (env wins)."""
    raw = _load_yaml_context()
    yaml_configured = bool(raw)
    budget_raw = _nested_dict(raw, "budget")
    turn_raw = _nested_dict(raw, "turn_budget")
    tool_raw = _nested_dict(raw, "tool_prune")
    walk_raw = _nested_dict(raw, "instruction_walkup")

    budget = ContextBudgetSettings(
        output_reserve=_merged_int(
            raw,
            budget_raw,
            "output_reserve",
            "BUTLER_CONTEXT_OUTPUT_RESERVE",
            CONTEXT_OUTPUT_RESERVE,
        ),
        compact_reserve=_merged_int(
            raw,
            budget_raw,
            "compact_reserve",
            "BUTLER_CONTEXT_COMPACT_RESERVE",
            CONTEXT_COMPACT_RESERVE,
        ),
        warning_buffer=_merged_int(
            raw,
            budget_raw,
            "warning_buffer",
            "BUTLER_CONTEXT_WARNING_BUFFER",
            CONTEXT_WARNING_BUFFER,
        ),
        error_buffer=_merged_int(
            raw,
            budget_raw,
            "error_buffer",
            "BUTLER_CONTEXT_ERROR_BUFFER",
            CONTEXT_ERROR_BUFFER,
        ),
        blocking_buffer=_merged_int(
            raw,
            budget_raw,
            "blocking_buffer",
            "BUTLER_CONTEXT_BLOCKING_BUFFER",
            CONTEXT_BLOCKING_BUFFER,
        ),
        compact_max_failures=_merged_int(
            raw,
            budget_raw,
            "compact_max_failures",
            "BUTLER_CONTEXT_COMPACT_MAX_FAILURES",
            CONTEXT_COMPACT_MAX_FAILURES,
            min=1,
        ),
    )

    turn_enabled_yaml = _bool_from_raw(turn_raw, "enabled", True)
    turn_enabled = env_truthy("BUTLER_TURN_TOKEN_BUDGET", default=turn_enabled_yaml)

    turn_budget = TurnBudgetSettings(
        enabled=turn_enabled,
        default_tokens=_merged_int(
            raw,
            turn_raw,
            "default",
            "BUTLER_TURN_BUDGET_DEFAULT",
            TURN_BUDGET_DEFAULT,
            min=1,
        ),
        min_iterations=_merged_int(
            raw,
            turn_raw,
            "min_iterations",
            "BUTLER_TURN_BUDGET_MIN_ITERATIONS",
            TURN_BUDGET_MIN_ITERATIONS,
            min=1,
        ),
        max_iterations=_merged_int(
            raw,
            turn_raw,
            "max_iterations",
            "BUTLER_TURN_BUDGET_MAX_ITERATIONS",
            TURN_BUDGET_MAX_ITERATIONS,
            min=1,
        ),
        max_continuations=_merged_int(
            raw,
            turn_raw,
            "max_continuations",
            "BUTLER_TURN_BUDGET_MAX_CONTINUATIONS",
            _TURN_BUDGET_MAX_CONTINUATIONS,
            min=1,
        ),
        min_delta=_merged_int(
            raw,
            turn_raw,
            "min_delta",
            "BUTLER_TURN_BUDGET_MIN_DELTA",
            _TURN_BUDGET_MIN_DELTA,
            min=0,
        ),
    )

    backward_yaml = _bool_from_raw(tool_raw, "backward_enabled", True)
    backward_enabled = env_truthy("BUTLER_TOOL_PRUNE_BACKWARD", default=backward_yaml)

    clear_at_least_env = os.getenv("BUTLER_TOOL_PRUNE_CLEAR_AT_LEAST", "").strip()
    backward_minimum = _merged_int(
        raw,
        tool_raw,
        "backward_minimum",
        "BUTLER_TOOL_PRUNE_BACKWARD_MINIMUM",
        _TOOL_PRUNE_BACKWARD_MINIMUM,
    )
    if clear_at_least_env:
        backward_minimum = int_env(
            "BUTLER_TOOL_PRUNE_CLEAR_AT_LEAST",
            backward_minimum,
            min=0,
        )

    tool_prune = ToolPruneSettings(
        keep_recent=_merged_int(
            raw,
            tool_raw,
            "keep_recent",
            "BUTLER_TOOL_PRUNE_KEEP_RECENT",
            TOOL_PRUNE_KEEP_RECENT,
            min=1,
        ),
        pim_keep_recent=_merged_int(
            raw,
            tool_raw,
            "pim_keep_recent",
            "BUTLER_TOOL_PRUNE_PIM_KEEP_RECENT",
            TOOL_PRUNE_PIM_KEEP_RECENT,
            min=1,
        ),
        pii_chars=_merged_int(
            raw,
            tool_raw,
            "pii_chars",
            "BUTLER_TOOL_PRUNE_PII_CHARS",
            TOOL_PRUNE_PII_CHARS,
            min=100,
        ),
        clearable_chars=_merged_int(
            raw,
            tool_raw,
            "clearable_chars",
            "BUTLER_TOOL_PRUNE_CLEARABLE_CHARS",
            TOOL_PRUNE_CLEARABLE_CHARS,
            min=200,
        ),
        preserve_chars=_merged_int(
            raw,
            tool_raw,
            "preserve_chars",
            "BUTLER_TOOL_PRUNE_PRESERVE_CHARS",
            TOOL_PRUNE_PRESERVE_CHARS,
            min=400,
        ),
        default_chars=_merged_int(
            raw,
            tool_raw,
            "default_chars",
            "BUTLER_TOOL_PRUNE_DEFAULT_CHARS",
            TOOL_PRUNE_DEFAULT_CHARS,
            min=200,
        ),
        backward_enabled=backward_enabled,
        backward_minimum=backward_minimum,
        backward_protect=_merged_int(
            raw,
            tool_raw,
            "backward_protect",
            "BUTLER_TOOL_PRUNE_BACKWARD_PROTECT",
            _TOOL_PRUNE_BACKWARD_PROTECT,
        ),
    )

    walk_enabled_yaml = _bool_from_raw(walk_raw, "enabled", True)
    walk_enabled = env_truthy("BUTLER_INSTRUCTION_WALKUP", default=walk_enabled_yaml)

    instruction_walkup = InstructionWalkupSettings(
        enabled=walk_enabled,
        max_chars=_merged_int(
            raw,
            walk_raw,
            "max_chars",
            "BUTLER_INSTRUCTION_WALKUP_MAX_CHARS",
            INSTRUCTION_WALKUP_MAX_CHARS,
        ),
        max_files=_merged_int(
            raw,
            walk_raw,
            "max_files",
            "BUTLER_INSTRUCTION_WALKUP_MAX_FILES",
            INSTRUCTION_WALKUP_MAX_FILES,
            min=1,
        ),
    )

    return ContextConfig(
        budget=budget,
        turn_budget=turn_budget,
        tool_prune=tool_prune,
        instruction_walkup=instruction_walkup,
        yaml_configured=yaml_configured,
    )


def format_context_config_source_line() -> str:
    """One-line effective context stack summary for ``/诊断``."""
    cfg = resolve_context_config()
    source = "yaml+env" if cfg.yaml_configured else "env/默认"
    b = cfg.budget
    return (
        f"上下文配置: 压缩缓冲={b.compact_reserve}, 轮预算="
        f"{'开' if cfg.turn_budget.enabled else '关'}, "
        f"工具剪枝 keep={cfg.tool_prune.keep_recent}, "
        f"walkup={'开' if cfg.instruction_walkup.enabled else '关'}, "
        f"来源={source}"
    )


__all__ = [
    "ContextBudgetSettings",
    "ContextConfig",
    "InstructionWalkupSettings",
    "ToolPruneSettings",
    "TurnBudgetSettings",
    "format_context_config_source_line",
    "resolve_context_config",
]
