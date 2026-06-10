# 环境变量 / Feature Flag 可维护性（2026-06）

> **性质**：纯工程梳理（Phase A）；**不**改产品边界，**不**改公理/定理证明正文。  
> **关联**：[`model-config-maintainability-2026-06.md`](model-config-maintainability-2026-06.md) · [`config/reference.md`](../../config/reference.md) · 深度审计 R7/R8  
> **登记册**：改动默认归类 **G3（文档同步）** 或 **无变更（搬迁）**；若静默改运行时默认 → **G4 风险**

---

## 1. 目标

1. `BUTLER_*` 默认字面量收口到 `butler/defaults/env_defaults.py`（按域分组）。  
2. `docs/config/reference.md`、`.env.example` 与代码 **一致**（以代码现值为 SSOT，不顺手「改回」旧文档数值）。  
3. `config_service` 白名单元数据默认与运行时 `getenv` 默认对齐。

---

## 2. 理论边界（强制）

以下约束适用于 **Phase A 全阶段**（含 A1）：

1. **禁止修改运行时默认语义**：本阶段不得改变任何 `os.getenv(name, default)` / `env_truthy(name, default=…)` / `_int_env(name, default)` 中 **default 的数值或布尔含义**。允许的唯一操作是：把已有字面量 **原样搬迁** 到 `env_defaults.py` 再 import。  
2. **文档跟随代码，而非反过来**：`reference.md` 漂移清扫时，以搬迁后的 `env_defaults` 为权威；**不得**为对齐旧文档而改代码默认（避免未声明地影响 **T1** 上下文阈值、**T2** 队列、**G2-03** 路由等前提测试）。  
3. **门控 / 权限 / Lead 工具隔离**：Phase A **不**改 `human_gate`、`owner_gate`、`permissions`、`project_tools._butler_allowed_tools` 等路径（**A3/A4/T6/T8**）。  
4. **config_service 白名单**：Phase A **不**把 Sprint 9 已移出的安全类 key 加回可运行时修改列表。  
5. **验证守门**：每批 PR 至少跑  
   `pytest tests/test_butler_config.py tests/test_env_defaults_phase_a1.py tests/test_context_budget.py -q`  
   （存在时）及 `pytest tests/test_premise_v3_new.py -q` 中与 T1 相关子集；动 gateway 默认时加 `test_message_queue.py`。

**例外（仅元数据，非 getenv）**：`config_service._register(..., default=…)` 可与 `env_defaults` 对齐（如 `BUTLER_ONBOARDING_WELCOME` 与 `handler_helpers` 一致为 `1`），因不改变未设 env 时的运行时分支。

---

## 3. 分期

| 阶段 | 内容 | 状态 |
|------|------|------|
| **A1** | R7 Top 漂移项：context / turn_budget / tool_prune / walkup / circuit / completion_notify / onboarding + `env_defaults.py` | ✅ 2026-06-09 |
| A2 | `config-surfaces.md`（env / secrets / yaml / config_service） | ✅ 2026-06-09 |
| A3 | 其余 R7 项与 `meta_flags` 等域索引 | ✅ 2026-06-09 |
| **B1** | `gateway.queue` yaml 段 + `resolve_gateway_queue_config` | ✅ 2026-06-09 |
| **B2** | `memory:` yaml 段 + `resolve_memory_config` | ✅ 2026-06-09 |
| **C1–C4** | 诊断入口 / 项目激活 / 扩展路径 / 门控栈文档矩阵 | ✅ 2026-06-09 |

---

## 4. A1 范围（R7 对照）

| env | 代码 SSOT（搬迁前） | reference 旧值 |
|-----|---------------------|----------------|
| `BUTLER_CONTEXT_OUTPUT_RESERVE` | 20000 | 16384 |
| `BUTLER_CONTEXT_COMPACT_RESERVE` | 13000 | 32768 |
| `BUTLER_CONTEXT_WARNING_BUFFER` | 20000 | 4096 |
| `BUTLER_CONTEXT_ERROR_BUFFER` | 20000 | 2048 |
| `BUTLER_CONTEXT_BLOCKING_BUFFER` | 3000 | 1024 |
| `BUTLER_PROVIDER_CIRCUIT_OPEN_SECONDS` | 120 | 60 |
| `BUTLER_TURN_BUDGET_DEFAULT` | 500000 | 200000 |
| `BUTLER_TURN_BUDGET_MAX_ITERATIONS` | 60 | 50 |
| `BUTLER_TOOL_PRUNE_*` | 4/400/2400/800 | 3/100/2000/600 |
| `BUTLER_INSTRUCTION_WALKUP_MAX_CHARS` | 4000 | 2000 |
| `BUTLER_INSTRUCTION_WALKUP_MAX_FILES` | 3 | 8 |
| `BUTLER_GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS` | 90 | 10 |
| `BUTLER_ONBOARDING_WELCOME` | runtime `"1"` | 表内 0 与 1 重复 |

---

## 5. A3 范围（R7 对照）

| 项 | 处理 |
|----|------|
| R7-8 | `DELEGATE_COMPLETION_MAX_EACH` reference 改为 3 次 |
| R7-13 | 删除 `BUTLER_MEMORY_OBSERVATION_TTL_DAYS` 重复行 |
| 域索引 | `butler/defaults/env_domains.py` + `docs/config/env-domains.md` |
| 默认搬迁 | `meta_flags` DAG、`confirm_flags` repair max、`completion_notify` max each、`observation_store` TTL、`queue_settings` cap/mode/drop |

---

## 6. B1 范围

| 项 | 处理 |
|----|------|
| YAML | `config.yaml` `gateway.queue.{mode,cap,drop,collect_debounce_ms}` |
| 解析 | `resolve_gateway_queue_config()`（`gateway_settings.py`），env 覆盖 yaml |
| 消费 | `queue_settings.py` 全局默认经 resolver；per-session `/queue` 覆盖不变 |
| 默认链 | env → yaml → `env_defaults.py` |

---

## 7. B2 范围

| 项 | 处理 |
|----|------|
| YAML | `config.yaml` `memory.*`（semantic、hybrid、index、ranking、observation、开关） |
| 解析 | `resolve_memory_config()`（`memory_settings.py`），env 覆盖 yaml |
| 消费 | `semantic_config`、`memory_caps`、`recall_layers`、`retrieval_ranking`、`observation_store` 等 |
| 诊断 | `format_memory_config_source_line()` → `/诊断` 记忆块 |

---

## 7b. B3 范围

| 项 | 处理 |
|----|------|
| YAML | `config.yaml` `gateway.inbound_media`（legacy 扁平 `gateway` 键仍算 yaml 来源） |
| 解析 | `resolve_gateway_inbound_config()` + `yaml_configured` 标志 |
| 诊断 | `format_gateway_inbound_config_source_line()` → `/诊断` 有效模型块（gateway 段） |

---

## 8. B4 范围

| 项 | 处理 |
|----|------|
| YAML | `config.yaml` `context.{budget,turn_budget,tool_prune,instruction_walkup}` |
| 解析 | `resolve_context_config()`（`context_settings.py`），env 覆盖 yaml |
| 消费 | `context_budget`、`turn_token_budget`、`tool_prune_policy`、`tool_output_prune`、`instruction_walkup` |
| 诊断 | `format_context_config_source_line()` → `/诊断` 上下文块 |
| 默认链 | env → yaml → `env_defaults.py` |

---

## 7c. B3b 范围（queue 诊断来源行）

| 项 | 处理 |
|----|------|
| YAML | `config.yaml` `gateway.queue` |
| 解析 | `resolve_gateway_queue_config()` + `yaml_configured` 标志 |
| 诊断 | `format_gateway_queue_config_source_line()` → `/诊断` 有效模型块；会话级仍用 `format_queue_status_line` |

---

## 8. Phase C 范围（文档矩阵）

| 项 | 交付 |
|----|------|
| C1 | [`docs/ops/diagnostic-entrypoints.md`](../../ops/diagnostic-entrypoints.md) + help 文案区分 |
| C2 | [`docs/architecture/project-activation.md`](../../architecture/project-activation.md) |
| C3 | [`docs/architecture/extension-registry-paths.md`](../../architecture/extension-registry-paths.md) |
| C4 | [`docs/architecture/permission-gate-stack.md`](../../architecture/permission-gate-stack.md) |

---

## 8. R8 配置卫生（`project-deep-audit-2026-06-r1to8.md` §R8）

| ID | 项 | 状态 |
|----|-----|------|
| R8-3 | `init_dotenv()` 入口化；`get_butler_settings` / `main` / `gateway/runner` | ✅ 2026-06-09 |
| R8-5 | `int_env` / `float_env`；`butler/` 全量替换裸 `int(os.getenv)` | ✅ |
| R8-6 | dead config 清扫 + `scripts/check-dead-env.sh` | ✅ |
| R8-7 | 未文档化 env 补全 / 脚本专用段 / hook 注入说明 | ✅ |
| R8-8 | [`docs/config/security.md`](../../config/security.md) + `is_butler_prod()` | ✅ |
| R8-9 | `reference.md` 优先级表 | ✅ |
| R8-10/11 | `float_env` 越界 warning；push cooldown 最小 1s | ✅ |
| R8-13 | `env_truthy` 统一（design/hashline/rules/todo/walkup 等） | ✅ 2026-06-09 |
| R8-14 | `float_env` 全量；`butler/` 无裸 `float(os.getenv)` | ✅ 2026-06-09 |
| R8-6 CI | `check-dead-env.sh` 并入 `docs-lint.sh` + CONTRIBUTING | ✅ |
| R8-4/12/15/16 | 降级或保持（dotenv override、hashline 默认、hook 前缀、expense 双源） | — 未改 |

---

## 9. R7 文档清扫（`project-deep-audit-2026-06-r1to8.md` §R7）

| ID | 项 | 状态 |
|----|-----|------|
| R7-1～8、13 | env 漂移 / 重复行 | ✅ A1–A3 |
| R7-9 | README Provider 表 vs `providers.py`（9 家） | ✅ 2026-06-09 |
| R7-10 | v4「9 核心工具」→ 11 内置 + terminal 执行门控说明 | ✅ |
| R7-11/16 | `STRUCTURE.md` 树形图重排（`cli/`、`workflows/` 分行） | ✅ |
| R7-12 | `design.md §11+` → 附录（`DOCUMENTATION.md`、`docs/README.md`） | ✅ |
| R7-14 | `tool_guardrails` 中 `list_runtime_jobs` / `run_runtime_job` | ✅ 保留 + 注释（registry 仍注册） |
| R7-15 | `butler-five-reports-gate.sh` 纳入 PR-F1–F6 子集 | ✅ |
| R7-17 | `agent_loop` / Core 栈行数对齐实测 | ✅ |

---

## 10. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-06-09 | 初稿 + 理论边界节 |
| 2026-06-09 | 开工 A1 |
| 2026-06-09 | A2：`docs/config/config-surfaces.md` + reference 交叉引用 + doctor 凭证行 |
| 2026-06-09 | A3：`env_domains.py` + `env-domains.md`；R7-8/R7-13；workflow/confirm/queue/observation 默认搬迁 |
| 2026-06-09 | B1：`gateway.queue` yaml + `resolve_gateway_queue_config` |
| 2026-06-09 | B2：`memory:` yaml + `resolve_memory_config` + 诊断来源行 |
| 2026-06-09 | B3：`gateway.inbound_media` 诊断来源行 + `yaml_configured` |
| 2026-06-09 | B3b：`gateway.queue` 诊断来源行 + `yaml_configured` |
| 2026-06-09 | B4：`context:` yaml + `resolve_context_config` + 诊断来源行 |
| 2026-06-09 | C1–C4：诊断/激活/扩展/门控文档矩阵 + help 区分文案 |
| 2026-06-09 | R7 文档清扫：README/STRUCTURE/v4-architecture/gate 脚本/tool_guardrails 注释 |
| 2026-06-09 | R8：env_parse、init_dotenv、security.md、reference 优先级、check-dead-env |
| 2026-06-09 | R8 尾巴：float_env 全量、env_truthy 续、check-dead-env → docs-lint/CI |
