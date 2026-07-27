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

# --- Concurrent tool timeout ---
CONCURRENT_TOOL_TIMEOUT_S_DEFAULT: Final[float] = 420.0

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

# --- Gateway delegate push (delegate_push_dedup.py) ---
GATEWAY_DELEGATE_PUSH_DEDUP_DEFAULT: Final[bool] = True
GATEWAY_DEFER_DELEGATE_PUSH_DURING_INBOUND_DEFAULT: Final[bool] = True
GATEWAY_DELEGATE_PUSH_MAX_AGE_SECONDS: Final[float] = 600.0

# --- Gateway durable outbox (durable_outbox.py) ---
GATEWAY_DURABLE_OUTBOX_DEFAULT: Final[bool] = True
GATEWAY_DURABLE_OUTBOX_MAX: Final[int] = 200

# --- Gateway progressive stream (progressive_stream.py) ---
GATEWAY_PROGRESSIVE_STREAM_DEFAULT: Final[bool] = False
GATEWAY_PROGRESSIVE_MIN_CHARS: Final[int] = 240
GATEWAY_PROGRESSIVE_INTERVAL_SECONDS: Final[float] = 45.0

# --- Gateway misc (runner.py, human_gate.py, session_lifecycle.py, completion_policy.py) ---
GATEWAY_MESSAGE_QUEUE_DEFAULT: Final[bool] = True
GATEWAY_QUEUE_PERSIST_DEFAULT: Final[bool] = False
GATEWAY_EXTERNAL_ID_DEDUPE_DEFAULT: Final[bool] = True
GATEWAY_INFLIGHT_TTL_SECONDS: Final[int] = 60
GATEWAY_HANDLER_TIMEOUT_SECONDS: Final[float] = 600.0
GATEWAY_HANDLER_WORKERS: Final[int] = 2
GATEWAY_HUMAN_GATE_TTL_SECONDS: Final[float] = 3600.0
GATEWAY_SESSION_INITIALIZING_DEFAULT: Final[bool] = True
GATEWAY_SUPPRESS_COMPLETION_AFTER_MAIN_DEFAULT: Final[bool] = True
GATEWAY_DELEGATE_COMPLETION_MODE_DEFAULT: Final[str] = "last"
GATEWAY_DELEGATE_PROGRESS_MAX: Final[int] = 5
GATEWAY_DELEGATE_PROGRESS_SECONDS: Final[float] = 90.0
GATEWAY_PROGRESS_MAX_ACK_MESSAGES: Final[int] = 1
GATEWAY_STREAM_PREVIEW_DEFAULT: Final[bool] = False
GATEWAY_QUEUE_PUSH_VIA_BRIDGE_DEFAULT: Final[bool] = True
GATEWAY_QUEUE_DRAIN_PER_TURN: Final[int] = 1
GATEWAY_QUEUE_DRAIN_FOLLOWUP: Final[int] = 1
GATEWAY_TASK_MILESTONE_DEFAULT: Final[bool] = False
GATEWAY_TASK_MILESTONE_SECONDS: Final[float] = 90.0
GATEWAY_TASK_MILESTONE_MAX: Final[int] = 5
GATEWAY_TYPING_FETCH_TIMEOUT_SECONDS: Final[float] = 2.0
GATEWAY_SYSTEMD_UNIT: Final[str] = "butler-gateway.service"

# --- B9 dev engine (b9_live_tuning.py, b9_tiers.py, b9_oracle_fewshot.py) ---
B9_LIVE_TUNING_DEFAULT: Final[bool] = True
B9_ORACLE_FEWSHOT_DEFAULT: Final[bool] = True
B9_TIER2_GATE_ENABLED_DEFAULT: Final[bool] = True
B9_TIER2_GATE_MIN_PASSED: Final[int] = 2

# --- Coding strict mode (dev_tools.py, boundary_observability.py) ---
CODING_STRICT_DEFAULT: Final[bool] = False

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

# --- Safety & guard (injection_guard.py, bot_loop_guard.py, two_phase_confirm.py) ---
SAFETY_ADVERSARIAL_MARK_DEFAULT: Final[bool] = True
SAFETY_BOT_LOOP_GUARD_DEFAULT: Final[bool] = False
SAFETY_CONFIRM_WRITE_OPS_DEFAULT: Final[bool] = True

# --- Tool enablement (web_fetch.py, terminal_sandbox_diagnostics.py) ---
TOOL_ENABLE_TERMINAL_DEFAULT: Final[bool] = False
TOOL_ENABLE_WEB_FETCH_DEFAULT: Final[bool] = False
TOOL_ENABLE_DATA_QUERY_DEFAULT: Final[bool] = False

# --- Workflow & routing (workflow_registry.py, corpus_routing.py) ---
WORKFLOW_AUTO_CONTINUE_DEFAULT: Final[bool] = True
WORKFLOW_AUTO_REVIEW_DEFAULT: Final[bool] = True
ROUTING_CORPUS_DEFAULT: Final[bool] = False
ROUTING_DESIGN_CONTEXT_INJECT_DEFAULT: Final[bool] = False

# --- Grounding & reasoning (grounding.py, ask_clarification.py) ---
GROUNDING_CALC_DEFAULT: Final[bool] = False
GROUNDING_API_MESSAGE_ACL_DEFAULT: Final[bool] = False
REASONING_ASK_CLARIFICATION_DEFAULT: Final[bool] = False

# --- CC features (context_compressor.py) ---
CC_BRIDGE_DEFAULT: Final[bool] = True
CC_ROUTE_HINTS_DEFAULT: Final[bool] = False
CC_COMPACT_SKILL_PRESERVE_DEFAULT: Final[bool] = False

# --- Batch & cache (tool_batch.py, delegate_cache.py) ---
BATCH_STALE_GUARD_DEFAULT: Final[bool] = True
CACHE_SAFE_DELEGATE_DEFAULT: Final[bool] = False

# --- Doom loop & bind (doom_loop.py, project_bind.py) ---
DOOM_LOOP_SOFT_NUDGE_DEFAULT: Final[bool] = False
BIND_DEFAULT_PROJECT_DEFAULT: Final[bool] = False

# --- Exec policy ---
EXECPOLICY_DEFAULT: Final[bool] = True
EXECUTE_CODE_DEFAULT: Final[bool] = False
EXECUTE_CODE_ALLOW_NETWORK_DEFAULT: Final[bool] = False

# --- Experience & experiment ---
EXPERIENCE_MERGE_DEFAULT: Final[bool] = True
EXPERIMENT_MODE_DEFAULT: Final[bool] = False
EXPERIMENT_GIT_RESET_DEFAULT: Final[bool] = False
EXPERIMENT_LEDGER_DEFAULT: Final[bool] = True

# --- Export ---
EXPORT_SEND_WECHAT_FILE_DEFAULT: Final[bool] = True

# --- Hashline & finish ---
HASHLINE_READ_DEFAULT: Final[bool] = False
HASHLINE_PATCH_DEFAULT: Final[bool] = True
FINISH_TOOL_TRUNCATE_ENABLED_DEFAULT: Final[bool] = True
FINISH_TOOL_TRUNCATE_MAX_DEFAULT: Final[int] = 5000

# --- Runtime ---
RUNTIME_TASK_STALE_AUTO_FAIL_DEFAULT: Final[bool] = False
RUNTIME_CC_BRIDGE_DEFAULT: Final[bool] = False
RUNTIME_ENABLED_DEFAULT: Final[str] = "1"
RUNTIME_PUSH_DEFAULT: Final[str] = "1"
RUNTIME_PUSH_COOLDOWN_SECONDS_DEFAULT: Final[str] = "25"
RUNTIME_PUSH_DRAIN_COOLDOWN_SECONDS_DEFAULT: Final[str] = "300"
RUNTIME_PUSH_QUEUE_DEFAULT: Final[str] = "1"
CC_CLI_DEFAULT: Final[str] = ""
EXPERIENCE_PRUNE_DAYS_DEFAULT: Final[str] = "30"

# --- Hooks ---
HOOKS_FAIL_CLOSED_DEFAULT: Final[bool] = False

# --- Transport ---
TRANSPORT_CACHE_CONTROL_DEFAULT: Final[bool] = True
TRANSPORT_STREAM_PROBE_DEFAULT: Final[bool] = False
TRANSPORT_TOOL_WIRE_DEFAULT: Final[bool] = True
TRANSPORT_THINKING_PROTOCOL_DEFAULT: Final[bool] = False
TRANSPORT_STREAMING_TOOLS_DEFAULT: Final[bool] = True
THINKING_BETA_MATRIX_DEFAULT: Final[str] = ""
THINKING_BETA_HEADER_DEFAULT: Final[str] = ""
STREAM_MEMORY_SCRUB_DEFAULT: Final[str] = "1"
PROVIDER_FAILOVER_DEFAULT: Final[str] = ""

# --- Permissions ---
PERMISSIONS_PARAM_BLACKLIST_DEFAULT: Final[bool] = True

# --- Project ---
PROJECT_BIND_DEFAULT_PROJECT_DEFAULT: Final[bool] = False
PROJECT_WORKTREE_DEFAULT: Final[bool] = False

# --- Dev engine ---
DEV_REFLECTION_CLOSURE_WRITE_DEFAULT: Final[bool] = False
DEV_REFLEXION_WRITE_EXPERIENCE_DEFAULT: Final[bool] = False

# --- MCP ---
MCP_TOOLS_ENGINE_DEFAULT: Final[bool] = True
MCP_TOOLS_ENGINE_FORCE_OFF_DEFAULT: Final[bool] = False
MCP_TOOLS_ENGINE_SSOT_DEFAULT: Final[bool] = False
MCP_PROFILES_DEFAULT: Final[bool] = True
MCP_GITHUB_ISSUE_LIST_DIRECT_DEFAULT: Final[bool] = True
MCP_GITHUB_REPO_LIST_DIRECT_DEFAULT: Final[bool] = True
MCP_TODOIST_PROJECT_LIST_DIRECT_DEFAULT: Final[bool] = True

# --- Gateway owner gates ---
OWNER_WECHAT_ID_DEFAULT: Final[str] = ""
PROJECT_CREATE_OPEN_DEFAULT: Final[str] = ""

# --- Permissions ---
WORKFLOW_AUTO_RESUME_DEFAULT: Final[str] = "0"

# --- Project ---
DEFAULT_PROJECT_DEFAULT: Final[str] = ""
LEAD_PROJECTS_DEFAULT: Final[str] = ""
PROJECT_DELETE_MATURITY_GATE_DEFAULT: Final[str] = "1"
TOOL_SAFE_ROOT_DEFAULT: Final[str] = ""

# --- Ops: snapshot flags (string defaults for raw display) ---
SEMANTIC_MEMORY_DEFAULT: Final[str] = "0"
QUEUE_PREFETCH_DEFAULT: Final[str] = "0"
WECHAT_DEV_SMOKE_DEFAULT: Final[str] = "0"
ENABLE_TERMINAL_DEFAULT: Final[str] = "0"
ENABLE_GIT_DEFAULT: Final[str] = "0"
ENABLE_GIT_WRITE_DEFAULT: Final[str] = "0"

# --- Configuration: secrets ---
SECRETS_FILE_DEFAULT: Final[str] = "1"
SECRETS_PATH_DEFAULT: Final[str] = ""
SECRETS_ENCRYPT_KEY_DEFAULT: Final[str] = ""

# --- Configuration: settings ---
PROJECTS_DIR_DEFAULT: Final[str] = ""
LOG_LEVEL_DEFAULT: Final[str] = ""
ENV_DEFAULT: Final[str] = ""

# --- Configuration: gateway inbound ---
MINIMAX_API_HOST_DEFAULT: Final[str] = ""
PREFER_ILINK_TEXT_DEFAULT: Final[str] = ""
STT_PROVIDER_DEFAULT: Final[str] = ""
WHISPER_MODEL_DEFAULT: Final[str] = ""

# --- Configuration: context ---
TOOL_PRUNE_CLEAR_AT_LEAST_DEFAULT: Final[str] = ""
DOOM_LOOP_MODE_DEFAULT: Final[str] = "block"

# --- Configuration: memory ---
FTS_HYBRID_WEIGHT_DEFAULT: Final[str] = ""
OBSERVATION_TTL_DAYS_DEFAULT: Final[str] = ""
MEMORY_OBSERVATION_MAX_ROWS_DEFAULT: Final[str] = ""
SYNC_CONVERSATION_MEMORY_DEFAULT: Final[str] = "0"

# --- Gateway: misc ---
BOT_LOOP_WHITELIST_DEFAULT: Final[str] = ""
EXPORT_SEND_WECHAT_MAX_BYTES_DEFAULT: Final[str] = ""
ENV_PROFILE_DEFAULT: Final[str] = ""
DATA_HOME_DEFAULT: Final[str] = ""
MCP_ENABLED_DEFAULT: Final[str] = "0"
VISION_FALLBACK_DEFAULT: Final[str] = "openai,ocr"

# --- MCP: misc ---
MCP_STDIO_ALLOW_COMMANDS_DEFAULT: Final[str] = "python,python3,uvx"
MCP_HTTP_HOSTS_ALLOW_DEFAULT: Final[str] = ""
MCP_CONFIG_DEFAULT: Final[str] = ""
MCP_TOOL_PREFIX_DEFAULT: Final[str] = "mcp"

# --- Eval / Observability ---
LANGFUSE_ENABLED_DEFAULT: Final[str] = "0"
GITHUB_DEFAULT_OWNER_DEFAULT: Final[str] = "XiaZiHunDun"
LOBEHUB_LOCALE_DEFAULT: Final[str] = "zh-CN"
MCP_CATALOG_URLS_DEFAULT: Final[str] = ""
SKILL_AUTO_SYNC_PROJECT_DEFAULT: Final[str] = "1"

# --- Ops: deploy profile ---
DEPLOY_PROFILE_DEFAULT: Final[str] = ""

# --- Ops: gateway / misc ---
CC_BRIDGE_DEFAULT: Final[str] = "0"
GATEWAY_ALLOWLIST_DEFAULT: Final[str] = ""
MCP_HTTP_ALLOW_PRIVATE_DEFAULT: Final[str] = "0"
DISABLE_AUTO_COMPACT_DEFAULT: Final[str] = ""

# --- Ops: terminal ---
TERMINAL_PROFILE_DEFAULT: Final[str] = "(默认)"

# --- Ops: eval ---
EVAL_PROD_EVIDENCE_DEFAULT: Final[str] = "1"
EVAL_HARD_FEEDBACK_DEFAULT: Final[str] = "1"
EVAL_B9_IN_REGRESSION_DEFAULT: Final[str] = "1"
EVAL_LLM_BENCHMARK_DEFAULT: Final[str] = "0"
EVAL_CAPTURE_DELEGATE_FAILURES_DEFAULT: Final[str] = ""
EVAL_DELEGATE_JUDGE_DEFAULT: Final[str] = "heuristic"

# --- Ops: langfuse tracer ---
PROJECT_NAME_DEFAULT: Final[str] = "butler-v4"
TENANT_DEFAULT: Final[str] = ""

# --- Ops: boundary observability ---
EMBEDDING_PROVIDER_DEFAULT: Final[str] = "local"

# --- Ops: morning brief ---
MORNING_BRIEF_DEFAULT: Final[str] = "0"

# --- Ops: secrets contract ---
SECRETS_GATEWAY_EXPECTED_DEFAULT: Final[str] = ""

# --- Ops: cost calibration ---
COST_CALIBRATION_PERSIST_DEFAULT: Final[str] = "1"

# --- Ops: token cost ---
TOKEN_COST_ESTIMATE_DEFAULT: Final[str] = ""

# --- Core: goal loop (goal_loop.py) ---
GOAL_LOOP_DEFAULT: Final[str] = "0"

# --- Core: context budget (context_budget.py) ---
DISABLE_COMPACT_DEFAULT: Final[str] = ""

# --- Core: context compressor (context_compressor.py) ---
TOKEN_COUNTER_DEFAULT: Final[str] = "heuristic"
COMPRESS_TOOL_RESPONSE_BUDGET_DEFAULT: Final[str] = ""

# --- Core: agents / design md sections (agents_md_sections.py, design_md_sections.py) ---
POST_COMPACT_AGENTS_SECTIONS_DEFAULT: Final[str] = ""
POST_COMPACT_DESIGN_SECTIONS_DEFAULT: Final[str] = ""
DESIGN_PRESET_DIR_DEFAULT: Final[str] = ""

# --- Core: meta flags (meta_flags.py) ---
WORKFLOW_MAX_PARALLEL_DEFAULT: Final[str] = ""

# --- Core: remote compact (remote_compact.py) ---
REMOTE_COMPACT_URL_DEFAULT: Final[str] = ""

# --- Core: transcript index (transcript_index.py) ---
TRANSCRIPT_INDEX_MIN_BYTES_DEFAULT: Final[str] = ""

# --- Core: tool result storage (tool_result_storage.py) ---
TOOL_RESULT_SPILL_MIN_CHARS_DEFAULT: Final[str] = ""
TOOL_RESULT_THRESHOLDS_DEFAULT: Final[str] = ""
TOOL_RESULT_MESSAGE_MAX_CHARS_DEFAULT: Final[str] = ""

# --- Core: tool pair repair (tool_pair_repair.py) ---
TOOL_PAIR_REPAIR_DEFAULT: Final[str] = "1"

# --- Core: fact extraction (fact_extraction.py) ---
FACT_EXTRACTION_DEFAULT: Final[str] = "1"

# --- Core: memory recap line (memory_recap_line.py) ---
MEMORY_RECAP_MIN_CHARS_DEFAULT: Final[str] = "300"

# --- Core: intent keywords (intent_keywords.py) ---
INTENT_KEYWORDS_DEFAULT: Final[str] = ""
INTENT_KEYWORDS_OFF_DEFAULT: Final[str] = ""

# --- Core: tool executor (tool_executor.py) ---
CONCURRENT_TOOL_TIMEOUT_S_STR_DEFAULT: Final[str] = ""

# --- Core: agent loop conversation (loop_conversation.py) ---
CONVERSATION_STATE_PERSIST_DEFAULT: Final[str] = "1"

# --- Tools: terminal sandbox ---
SANDBOX_CREDENTIAL_ENV_DEFAULT: Final[str] = ""

# --- Tools: download ---
ENABLE_DOWNLOAD_DEFAULT: Final[str] = ""
DOWNLOAD_MAX_BYTES_DEFAULT: Final[str] = ""
DOWNLOAD_ALLOW_HOSTS_DEFAULT: Final[str] = ""

# --- Tools: audit ---
TOOL_AUDIT_PERSIST_DEFAULT: Final[str] = "1"
TOOL_AUDIT_JSONL_DEFAULT: Final[str] = ""
TOOL_AUDIT_PATH_DEFAULT: Final[str] = ""

# --- Tools: scope ---
TOOL_SCOPE_DEFAULT: Final[str] = "environment"
WORKSPACE_ANCHOR_STRICT_DEFAULT: Final[str] = "1"
TOOL_PROJECT_ANCHOR_DEFAULT: Final[str] = "1"

# --- Tools: terminal allowlist extra ---
TERMINAL_ALLOWLIST_EXTRA_DEFAULT: Final[str] = ""

# --- Tools: PIM encryption ---
PIM_ENCRYPT_DEFAULT: Final[str] = "0"
PIM_ENCRYPT_KEY_DEFAULT: Final[str] = ""

# --- Tools: default project env ---
DEFAULT_PROJECT_ENV_DEFAULT: Final[str] = ""

# --- Tools: git push ---
ENABLE_GIT_PUSH_DEFAULT: Final[str] = ""

# --- Tools: MCP self-service ---
MCP_SELF_SERVICE_DEFAULT: Final[str] = "1"

# --- Memory: experience mining ---
EXPERIENCE_MINING_DEFAULT: Final[str] = "1"
EXPERIENCE_MINING_AUTO_INGEST_DEFAULT: Final[str] = ""

# --- Memory: markdown chunking ---
MARKDOWN_INDEX_PATHS_DEFAULT: Final[str] = ""

# --- Memory: owner write approval ---
MEMORY_WRITE_APPROVAL_DEFAULT: Final[str] = "owner_scopes"

# --- Memory: project memory classifiers ---
MEMORY_AUTO_APPROVE_DEFAULT: Final[str] = ""

# --- Memory: semantic config (env-only defaults, distinct from YAML defaults) ---
EMBEDDING_PROVIDER_ENV_DEFAULT: Final[str] = ""
EMBEDDING_MODEL_ENV_DEFAULT: Final[str] = ""

# --- Home ---
BUTLER_HOME_DEFAULT: Final[str] = "~/.butler"

# --- Dev engine (dev_tools.py, loop_plugin.py, verify.py, b9_delegate_gate.py, gentc_mutation.py) ---
DEV_ENGINE_DEFAULT: Final[str] = "1"
DEV_AUTO_VERIFY_DEFAULT: Final[str] = "1"
DEV_ROLLBACK_ENABLED_DEFAULT: Final[str] = "1"
DEV_DIAGNOSTICS_INJECT_DEFAULT: Final[str] = "1"
DEV_AUTO_REVIEW_DEFAULT: Final[str] = "0"
DEV_REVIEW_STRICT_DEFAULT: Final[str] = "0"
DEV_VERIFY_FIX_PIN_DEFAULT: Final[str] = "1"
DEV_AUTO_VERIFY_LEVELS_DEFAULT: Final[str] = "lint,test"
DEV_VERIFY_SUCCESS_GATE_DEFAULT: Final[str] = "1"
DEV_VERIFY_TIMEOUT_DEFAULT: Final[int] = 300
GENTC_MUTATION_MIN_SCORE_DEFAULT: Final[str] = "0.6"

# --- Skills (injection_policy.py, router_ops.py, paths.py, skills_project_sync.py, github.py) ---
SKILL_REGISTRY_DEFAULT: Final[str] = "1"
SKILL_REGISTRY_SOURCES_DEFAULT: Final[str] = "bundled,project,github,url,clawhub,marketplace,lobehub"
REGISTRY_AUTO_INSTALL_DEFAULT: Final[str] = ""
SKILL_TRUSTED_REPOS_DEFAULT: Final[str] = ""
SKILL_AUTO_SYNC_PROJECT_DEFAULT: Final[str] = "1"
SKILL_INJECTION_MODE_DEFAULT: Final[str] = "fallback"
SKILL_SEMANTIC_ROUTING_DEFAULT: Final[str] = "1"

# --- LobeHub (lobehub.py) ---
LOBEHUB_ENABLED_DEFAULT: Final[str] = "1"
LOBEHUB_URL_DEFAULT: Final[str] = "https://market.lobehub.com"
LOBEHUB_TOKEN_DEFAULT: Final[str] = ""
LOBEHUB_USE_CLI_DEFAULT: Final[str] = ""
LOBEHUB_LOCALE_DEFAULT: Final[str] = "zh-CN"

# --- ClawHub (clawhub.py) ---
CLAWHUB_URL_DEFAULT: Final[str] = "https://clawhub.ai/api/v1"
CLAWHUB_ENABLED_DEFAULT: Final[str] = "1"

# --- Claude Marketplace (marketplace.py) ---
CLAUDE_MARKETPLACE_ENABLED_DEFAULT: Final[str] = "1"
CLAUDE_MARKETPLACE_URLS_DEFAULT: Final[str] = ""

# --- MCP misc (mcp_catalog.py, mcp_catalog_remote.py, mcp_project_tools.py) ---
MCP_CATALOG_URLS_DEFAULT: Final[str] = ""
MCP_CATALOG_DEFAULT: Final[str] = "1"
MCP_AUTO_PROJECT_TOOLS_DEFAULT: Final[str] = "1"

# --- Registry misc (url_safety.py) ---
REGISTRY_ALLOWED_HOSTS_DEFAULT: Final[str] = ""

# --- Gateway misc (inbound_idempotency.py, durable_outbox.py) ---
GATEWAY_INFLIGHT_TTL_SEC_DEFAULT: Final[str] = ""
GATEWAY_DURABLE_OUTBOX_MAX_DEFAULT: Final[str] = ""

# --- Eval (llm_delegate_benchmark.py) ---
EVAL_LLM_BENCHMARK_DEFAULT: Final[str] = "0"

# --- Eval (memory_mb_suite.py, b9_oracle_suite.py) ---
EVAL_MEM_PASS_RATE_MIN_DEFAULT: Final[float] = 0.7
EVAL_B9_PASS_RATE_MIN_DEFAULT: Final[float] = 1.0
