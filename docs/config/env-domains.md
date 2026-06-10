# Butler 环境变量域索引（Phase A3）

> **状态**：2026-06-09  
> **用途**：按功能域定位「谁读这个 env」与默认 SSOT；**不**替代 [`reference.md`](reference.md) 全量表。  
> **关联**：[`env_defaults.py`](../../butler/defaults/env_defaults.py) · [`env_domains.py`](../../butler/defaults/env_domains.py) · [`config-surfaces.md`](config-surfaces.md)

---

## 1. 怎么用

1. 改某个 `BUTLER_*` 的**默认数值** → 先查下表「默认 SSOT」列；数值类进 `butler/defaults/env_defaults.py`，布尔类留在各 `*_flags.py` 的 `env_truthy(..., default=…)`。  
2. 新增 env → 写入 `reference.md` + `.env.example`，并在下表（及 `env_domains.py`）登记域。  
3. 全量 env 列表仍以 [`reference.md`](reference.md) 为准。

---

## 2. 域一览

| 域 ID | 标题 | 模块 | 代表 env | 默认 SSOT |
|-------|------|------|----------|-----------|
| `context` | 上下文预算（T1） | `context_budget.py`, `preemptive_compact.py` | `BUTLER_CONTEXT_*_BUFFER`, `BUTLER_CONTEXT_OUTPUT_RESERVE` | `env_defaults.py` |
| `turn_budget` | 轮次 token 预算 | `turn_token_budget.py` | `BUTLER_TURN_BUDGET_*` | `env_defaults.py` |
| `tool_prune` | 工具输出 micro 剪枝 | `tool_prune_policy.py` | `BUTLER_TOOL_PRUNE_*` | `env_defaults.py` |
| `instruction_walkup` | read_file → AGENTS.md | `instruction_walkup.py` | `BUTLER_INSTRUCTION_WALKUP*` | `env_defaults.py` + 开关默认开 |
| `provider_circuit` | LLM 供应商熔断 | `provider_health.py`, `fallback.py` | `BUTLER_PROVIDER_CIRCUIT*` | `env_defaults.py` |
| `gateway_notify` | 完成/委派推送 | `completion_notify.py` | `BUTLER_GATEWAY_*_NOTIFY*`, `DELEGATE_COMPLETION_*` | `env_defaults.py`（阈值） |
| `gateway_queue` | 入站消息队列 | `gateway_settings.py`, `queue_settings.py` | `BUTLER_GATEWAY_QUEUE_*` | yaml `gateway.queue` ← env ← `env_defaults.py` |
| `meta` | Workflow DAG / 实验 | `meta_flags.py` | `BUTLER_WORKFLOW_MAX_PARALLEL`, `BUTLER_EXP_CACHE` | DAG 上限 → `env_defaults.py`；布尔 → `meta_flags.py` |
| `harness` | 线束 / MCP 延迟 | `harness_flags.py` | `BUTLER_MCP_DEFERRED_TOOLS`, `BUTLER_ASK_CLARIFICATION` | `harness_flags.py` |
| `workflow` | 工作流编排开关 | `workflow_flags.py`, `workflows/runner.py` | `BUTLER_WORKFLOW_RESCUE`, `AUTO_RESUME` | `workflow_flags.py` |
| `confirm` | 二次确认 / schema | `confirm_flags.py` | `BUTLER_TWO_PHASE_CONFIRM`, `OUTPUT_SCHEMA_REPAIR_MAX` | `REPAIR_MAX` → `env_defaults.py` |
| `memory_stack` | 记忆栈 | `memory_settings.py`, `semantic_config.py` | `BUTLER_SEMANTIC_MEMORY`, `BUTLER_VECTOR_HYBRID_WEIGHT` | yaml `memory.*` ← env ← `env_defaults.py` |
| `memory_observation` | Observation Store | `observation_store.py` | `BUTLER_OBSERVATION_TTL_DAYS`, `MEMORY_OBSERVER_QUEUE` | yaml `memory.observation` ← env |
| `onboarding` | 首次欢迎 | `handler_helpers.py`, `config_service.py` | `BUTLER_ONBOARDING_WELCOME` | `env_defaults.py` |
| `runtime_config` | 微信 `/config` 白名单 | `config_service.py`, `config_tools.py` | （子集见 `config-surfaces.md` §5） | 元数据 `meta.default` |

---

## 3. A3 文档勘误（R7）

| 项 | 修正 |
|----|------|
| R7-8 | `BUTLER_GATEWAY_DELEGATE_COMPLETION_MAX_EACH` 默认 **3 次**（非 500 字符） |
| R7-13 | 删除 `BUTLER_MEMORY_OBSERVATION_TTL_DAYS`；代码仅读 `BUTLER_OBSERVATION_TTL_DAYS`（未设时 90 天） |

---

## 4. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-06-09 | Phase A3：域索引 + `env_domains.py` + R7-8/R7-13 |
