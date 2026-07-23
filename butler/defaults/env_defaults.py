"""Centralized ``BUTLER_*`` env default literals (Phase A1).

Import these constants into ``os.getenv(..., str(X))`` call sites — do not
duplicate numeric defaults in business modules. Phase A rule: relocate only;
do not change values without a dedicated premise-test gate (see
``docs/plans/active/env-config-maintainability-2026-06.md`` §2).
"""

from __future__ import annotations

from typing import Final

# --- Context budget (T1 / CC autoCompact alignment) ---
CONTEXT_OUTPUT_RESERVE: Final[int] = 20_000
CONTEXT_COMPACT_RESERVE: Final[int] = 13_000
CONTEXT_WARNING_BUFFER: Final[int] = 20_000
CONTEXT_ERROR_BUFFER: Final[int] = 20_000
CONTEXT_BLOCKING_BUFFER: Final[int] = 3_000
CONTEXT_COMPACT_MAX_FAILURES: Final[int] = 3

# --- Gateway completion notify ---
GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS: Final[float] = 90.0
GATEWAY_MAX_SUPPLEMENTARY_PER_TURN: Final[int] = 2

# --- Provider circuit breaker ---
PROVIDER_CIRCUIT_DEFAULT: Final[bool] = True
PROVIDER_CIRCUIT_FAILURES: Final[int] = 3
PROVIDER_CIRCUIT_OPEN_SECONDS: Final[float] = 120.0

# --- Turn token budget ---
TURN_BUDGET_DEFAULT: Final[int] = 500_000
TURN_BUDGET_MAX_ITERATIONS: Final[int] = 60
TURN_BUDGET_MIN_ITERATIONS: Final[int] = 30
TURN_BUDGET_MAX_CONTINUATIONS: Final[int] = 3
TURN_BUDGET_MIN_DELTA: Final[int] = 500

# --- Turn summary line (turn_summary_line.py) ---
TURN_SUMMARY_LINE_DEFAULT: Final[bool] = True
TURN_SUMMARY_MIN_CHARS: Final[int] = 400

# --- Tool output prune ---
TOOL_PRUNE_KEEP_RECENT: Final[int] = 4
TOOL_PRUNE_PIM_KEEP_RECENT: Final[int] = 2
TOOL_PRUNE_PII_CHARS: Final[int] = 200
TOOL_PRUNE_CLEARABLE_CHARS: Final[int] = 400
TOOL_PRUNE_PRESERVE_CHARS: Final[int] = 2400
TOOL_PRUNE_DEFAULT_CHARS: Final[int] = 800

# --- Tool output masking ---
TOOL_MASK_PROTECT_TOKENS: Final[int] = 50_000
TOOL_MASK_MIN_PRUNABLE: Final[int] = 30_000

# --- Instruction walkup (read_file → AGENTS.md) ---
INSTRUCTION_WALKUP_MAX_CHARS: Final[int] = 4000
INSTRUCTION_WALKUP_MAX_FILES: Final[int] = 3

# --- Onboarding (runtime unset env → enabled) ---
ONBOARDING_WELCOME_DEFAULT: Final[str] = "1"

# --- Workflow / MetaGPT (meta_flags.py) ---
WORKFLOW_MAX_DAG_NODES: Final[int] = 50
WORKFLOW_MAX_DAG_PARALLEL: Final[int] = 5

# --- Confirm / schema repair (confirm_flags.py) ---
OUTPUT_SCHEMA_REPAIR_MAX: Final[int] = 2

# --- Gateway delegate completion push ---
GATEWAY_DELEGATE_COMPLETION_MAX_EACH: Final[int] = 3

# --- Memory observation store ---
OBSERVATION_TTL_DAYS: Final[int] = 90

# --- Delegate policy (delegate/policy.py, delegate_semaphore.py) ---
DELEGATE_ASYNC_DEFAULT: Final[bool] = True
DELEGATE_CONCURRENCY_LIMIT_DEFAULT: Final[bool] = True
DELEGATE_MAX_CONCURRENT: Final[int] = 2
DELEGATE_MAX_ITERATIONS: Final[int] = 24
DELEGATE_ONE_TOOL_PER_ITERATION_DEFAULT: Final[bool] = False
DELEGATE_SUMMARY_MAX_CHARS: Final[int] = 4000
DELEGATE_SUMMARY_RESERVE_RATIO: Final[float] = 0.0

# --- Compaction (turn_compaction.py, compaction_task.py, compaction_prompt.py) ---
COMPACTION_EXPLICIT_TURN_DEFAULT: Final[bool] = True
COMPACTION_INBOUND_BRIDGE_DEFAULT: Final[bool] = True
COMPACTION_PREFLIGHT_CHECKLIST_DEFAULT: Final[bool] = True
COMPACTION_PRESERVE_RECENT_RATIO: Final[float] = 0.25
COMPACTION_PRESERVE_RECENT_TOKENS_DEFAULT: Final[int] = 0
COMPACTION_SPLIT_TURN_DEFAULT: Final[bool] = True
COMPACTION_TAIL_TURNS: Final[int] = 2
COMPACTION_TURN_MIN_MSGS: Final[int] = 8
COMPACTION_USE_HERMES_TEMPLATE_DEFAULT: Final[bool] = False
COMPACTION_USE_OPENCODE_TEMPLATE_DEFAULT: Final[bool] = True
COMPACTION_USE_TURNS_DEFAULT: Final[bool] = True
COMPACTION_MIN_PRESERVE_RECENT: Final[int] = 2_000
COMPACTION_MAX_PRESERVE_RECENT: Final[int] = 8_000

# --- Terminal (terminal_sandbox.py, terminal_danger.py, terminal_approval.py) ---
TERMINAL_SANDBOX_DEFAULT: Final[bool] = False
TERMINAL_SANDBOX_NETWORK_ALLOWLIST_DEFAULT: Final[bool] = False
TERMINAL_SANDBOX_FAIL_UNAVAILABLE_DEFAULT: Final[bool] = False
TERMINAL_DANGER_CHECK_DEFAULT: Final[bool] = True
TERMINAL_REQUIRE_APPROVAL_DEFAULT: Final[bool] = False
TERMINAL_PIPE_DEFAULT: Final[bool] = False
TERMINAL_SMART_APPROVE_DEFAULT: Final[bool] = True
TERMINAL_PATTERN_APPROVE_TTL: Final[float] = 86400.0

# --- WeChat (wechat_text_export.py, adapter_outbound_ops.py) ---
WECHAT_ATTACH_MIN_CHARS: Final[int] = 400
WECHAT_ATTACH_BRIEF_CHARS: Final[int] = 280
WECHAT_ATTACH_DELEGATE_DEFAULT: Final[bool] = True
WECHAT_ATTACH_DETAIL_DEFAULT: Final[bool] = True
WECHAT_ATTACH_DIAGNOSTIC_DEFAULT: Final[bool] = True
WECHAT_ATTACH_RUNTIME_DEFAULT: Final[bool] = True
WECHAT_ATTACH_SUFFIX_DEFAULT: Final[str] = ".txt"
WECHAT_RATE_LIMIT_BACKOFF_MAX: Final[float] = 90.0

# --- CLI (session_ui.py, stream.py) ---
CLI_SHOW_REASONING_DEFAULT: Final[bool] = False
CLI_STREAM_MODE_DEFAULT: Final[str] = "live"

# --- Catalog (catalog_integrity.py) ---
CATALOG_INTEGRITY_DEFAULT: Final[bool] = True
CATALOG_INTEGRITY_FAIL_CLOSED_DEFAULT: Final[bool] = True

# --- Gateway inbound queue (queue_settings.py / gateway.queue yaml) ---
GATEWAY_QUEUE_CAP: Final[int] = 20
GATEWAY_DEFAULT_QUEUE_MODE: Final[str] = "followup"
GATEWAY_DEFAULT_QUEUE_DROP: Final[str] = "summarize"
GATEWAY_QUEUE_COLLECT_DEBOUNCE_MS: Final[int] = 500

# --- Memory stack (memory_settings.py / config.yaml memory.*) ---
MEMORY_VECTOR_HYBRID_WEIGHT: Final[float] = 0.5
MEMORY_SEMANTIC_SEARCH_LIMIT: Final[int] = 8
MEMORY_MAX_LINES: Final[int] = 200
MEMORY_MAX_BYTES: Final[int] = 25 * 1024
MEMORY_HALF_LIFE_DAYS: Final[float] = 30.0
MEMORY_ACCESS_BOOST: Final[float] = 0.12
