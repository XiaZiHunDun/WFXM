"""Feature-flag / env domain index (Phase A3).

Maps maintenance areas to owning modules and representative ``BUTLER_*`` keys.
Numeric defaults live in ``env_defaults.py``; boolean toggles use ``env_truthy``
defaults declared in each ``*_flags.py`` module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = ["EnvDomain", "ENV_DOMAINS", "domain_by_id"]


@dataclass(frozen=True)
class EnvDomain:
    """One configurable feature area."""

    domain_id: str
    title: str
    modules: tuple[str, ...]
    env_vars: tuple[str, ...]
    defaults_note: str


ENV_DOMAINS: Final[tuple[EnvDomain, ...]] = (
    EnvDomain(
        "context",
        "上下文预算（T1）",
        ("butler/core/context_budget.py", "butler/core/preemptive_compact.py"),
        (
            "BUTLER_CONTEXT_OUTPUT_RESERVE",
            "BUTLER_CONTEXT_COMPACT_RESERVE",
            "BUTLER_CONTEXT_WARNING_BUFFER",
            "BUTLER_CONTEXT_ERROR_BUFFER",
            "BUTLER_CONTEXT_BLOCKING_BUFFER",
            "BUTLER_CONTEXT_COMPACT_MAX_FAILURES",
        ),
        "数值默认 → butler/defaults/env_defaults.py",
    ),
    EnvDomain(
        "turn_budget",
        "轮次 token 预算",
        ("butler/core/turn_token_budget.py",),
        (
            "BUTLER_TURN_TOKEN_BUDGET",
            "BUTLER_TURN_BUDGET_DEFAULT",
            "BUTLER_TURN_BUDGET_MAX_ITERATIONS",
            "BUTLER_TURN_BUDGET_MIN_ITERATIONS",
        ),
        "数值默认 → env_defaults.py",
    ),
    EnvDomain(
        "tool_prune",
        "工具输出 micro 剪枝",
        ("butler/core/tool_prune_policy.py",),
        (
            "BUTLER_TOOL_PRUNE_KEEP_RECENT",
            "BUTLER_TOOL_PRUNE_CLEARABLE_CHARS",
            "BUTLER_TOOL_PRUNE_PRESERVE_CHARS",
            "BUTLER_TOOL_PRUNE_DEFAULT_CHARS",
        ),
        "数值默认 → env_defaults.py",
    ),
    EnvDomain(
        "instruction_walkup",
        "read_file → AGENTS.md 注入",
        ("butler/core/instruction_walkup.py",),
        (
            "BUTLER_INSTRUCTION_WALKUP",
            "BUTLER_INSTRUCTION_WALKUP_MAX_CHARS",
            "BUTLER_INSTRUCTION_WALKUP_MAX_FILES",
        ),
        "数值默认 → env_defaults.py；开关默认开",
    ),
    EnvDomain(
        "provider_circuit",
        "LLM 供应商熔断",
        ("butler/transport/provider_health.py", "butler/transport/fallback.py"),
        (
            "BUTLER_PROVIDER_CIRCUIT",
            "BUTLER_PROVIDER_CIRCUIT_FAILURES",
            "BUTLER_PROVIDER_CIRCUIT_OPEN_SECONDS",
        ),
        "数值默认 → env_defaults.py",
    ),
    EnvDomain(
        "gateway_notify",
        "网关完成/委派推送",
        ("butler/gateway/completion_notify.py",),
        (
            "BUTLER_GATEWAY_COMPLETION_NOTIFY",
            "BUTLER_GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS",
            "BUTLER_GATEWAY_DELEGATE_COMPLETION_MODE",
            "BUTLER_GATEWAY_DELEGATE_COMPLETION_MAX_EACH",
        ),
        "MIN_SECONDS / MAX_EACH → env_defaults.py",
    ),
    EnvDomain(
        "gateway_queue",
        "入站消息队列",
        (
            "butler/gateway_settings.py",
            "butler/gateway/queue_settings.py",
            "butler/gateway/message_queue.py",
        ),
        (
            "BUTLER_GATEWAY_QUEUE_MODE",
            "BUTLER_GATEWAY_QUEUE_CAP",
            "BUTLER_GATEWAY_QUEUE_DROP",
            "BUTLER_GATEWAY_QUEUE_COLLECT_DEBOUNCE_MS",
        ),
        "yaml gateway.queue ← env 覆盖 ← env_defaults.py；per-session 见 gateway_queue/*.json",
    ),
    EnvDomain(
        "meta",
        "Workflow DAG / 实验缓存",
        ("butler/core/meta_flags.py",),
        (
            "BUTLER_EXP_CACHE",
            "BUTLER_TOOL_RECALL_BM25",
            "BUTLER_WORKFLOW_CHECKPOINT",
            "BUTLER_OUTPUT_SCHEMA_VALIDATE",
            "BUTLER_WORKFLOW_MAX_PARALLEL",
        ),
        "DAG 上限常量 → env_defaults.py；布尔见 meta_flags env_truthy",
    ),
    EnvDomain(
        "harness",
        "线束 / MCP 延迟加载",
        ("butler/core/harness_flags.py",),
        (
            "BUTLER_MCP_DEFERRED_TOOLS",
            "BUTLER_ASK_CLARIFICATION",
            "BUTLER_STATIC_SYSTEM_REMINDER",
        ),
        "布尔默认见 harness_flags.py",
    ),
    EnvDomain(
        "workflow",
        "工作流编排开关",
        ("butler/core/workflow_flags.py", "butler/workflows/runner.py"),
        (
            "BUTLER_WORKFLOW_RESCUE",
            "BUTLER_WORKFLOW_OPTIONAL",
            "BUTLER_WORKFLOW_CLEAR_CHILD",
            "BUTLER_WORKFLOW_AUTO_RESUME",
        ),
        "布尔默认见 workflow_flags.py",
    ),
    EnvDomain(
        "confirm",
        "二次确认 / schema 修复",
        ("butler/core/confirm_flags.py",),
        (
            "BUTLER_TWO_PHASE_CONFIRM",
            "BUTLER_PERMISSION_RISK_HEURISTIC",
            "BUTLER_OUTPUT_SCHEMA_REPAIR",
            "BUTLER_OUTPUT_SCHEMA_REPAIR_MAX",
        ),
        "REPAIR_MAX → env_defaults.py",
    ),
    EnvDomain(
        "memory_stack",
        "记忆栈（语义/混合/衰减）",
        (
            "butler/memory_settings.py",
            "butler/memory/semantic_config.py",
            "butler/memory/memory_caps.py",
            "butler/memory/retrieval_ranking.py",
        ),
        (
            "BUTLER_SEMANTIC_MEMORY",
            "BUTLER_VECTOR_HYBRID_WEIGHT",
            "BUTLER_SEMANTIC_SEARCH_LIMIT",
            "BUTLER_MEMORY_MAX_LINES",
            "BUTLER_MEMORY_HALF_LIFE_DAYS",
            "BUTLER_MEMORY_ACCESS_BOOST",
        ),
        "yaml memory.* ← env 覆盖 ← env_defaults.py；嵌入见 embedding.*",
    ),
    EnvDomain(
        "memory_observation",
        "Observation Store",
        ("butler/memory/observation_store.py", "butler/memory/observer_queue.py"),
        (
            "BUTLER_MEMORY_OBSERVER_QUEUE",
            "BUTLER_OBSERVATION_TTL_DAYS",
            "BUTLER_MEMORY_OBSERVATION_MAX_ROWS",
        ),
        "yaml memory.observation ← env；解析经 resolve_memory_config",
    ),
    EnvDomain(
        "onboarding",
        "首次会话欢迎",
        ("butler/gateway/handler_helpers.py", "butler/config_service.py"),
        ("BUTLER_ONBOARDING_WELCOME",),
        "ONBOARDING_WELCOME_DEFAULT → env_defaults.py",
    ),
    EnvDomain(
        "runtime_config",
        "微信 /config 运行时白名单",
        ("butler/config_service.py", "butler/tools/config_tools.py"),
        (),
        "可写子集见 config_service._MUTABLE_KEYS；见 config-surfaces.md §5",
    ),
)


def domain_by_id(domain_id: str) -> EnvDomain | None:
    key = (domain_id or "").strip().lower()
    for d in ENV_DOMAINS:
        if d.domain_id == key:
            return d
    return None
