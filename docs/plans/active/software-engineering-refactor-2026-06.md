# 软件工程整理计划（复杂度 · 分层 · 测试）

> **状态**：立项 **2026-06-26**  
> **性质**：纯工程（**不**改产品边界；与 G1-04 观测窗 **并行**）  
> **登记**：[`roadmap-backlog`](../decisions/roadmap-backlog-and-boundaries-2026-05.md) §3.11  
> **证据**：[`project-deep-audit-2026-06-r1to8.md`](../../reviews/project-deep-audit-2026-06-r1to8.md) · [`model-config-maintainability-2026-06.md`](model-config-maintainability-2026-06.md) · [`agent-testing-strategy-2026-06.md`](../decisions/agent-testing-strategy-2026-06.md)

---

## 0. 目标

在 **不暂停 Owner 运营**（G1-04 窗至 07-31）的前提下，降低：

1. **单文件 / 单函数认知负担**（读改成本）  
2. **层间反向依赖**（CLI 测试必须拉 gateway）  
3. **静默降级**（记忆/embedding 塌方用户无感）  
4. **测试与生产 env 耦合**（全量 pytest 技术债）

**非目标**：重写 Loop、LangGraph 替换、IDE 级能力、为「漂亮」而大拆。

---

## 1. 当前基线（2026-06-29 命令验证）

| 指标 | 数值 | 说明 |
|------|------|------|
| `butler/` Python 文件 | ~453 | 与 06 审计同量级 |
| **>800 行** 单文件 | **2** | `coding_knowledge.py` 1613、`locked_phases.py` 826 |
| **>600 行** 单文件 | **~12** | `agent_loop_phases.py` 906；`wechat_ilink/__init__.py` ~1119 |
| `main.py` | **177** | ✅ R1-7 已薄化（原 1340） |
| `delegate_phases.py` | **125** | ✅ ENG-2 门面；阶段在 `delegate_phases/` 子包 |
| `delegate_impl.py` | **385** | ✅ R1-5 已拆出 `delegate_phases` |
| `wechat_ilink` | **子包** | ✅ PROD-P2-01 + ENG-5；**第三轮**见 [`wechat-ilink-round3-2026-06.md`](wechat-ilink-round3-2026-06.md) |
| 延迟 `from butler.` | **~3627** | 预算守门 `LAZY_IMPORT_BUDGET=3650` |
| `core/` → `gateway/` 顶层 import | **0** | ✅ R1-3：`events_sink` + AST 守门 |
| 全量 `pytest tests/` | **0 fail**（2026-06-27；6250 pass，排除 corpus） | 泄漏 + `.env` 耦合已修；发版 gate 绿 |
| `get_model_config` | 已委托 `resolve_effective_model` | P0-1 部分完成 |

### 1.1 已收口（勿重复立项）

| 项 | 状态 |
|----|------|
| `main.py` CLI 拆分 | ✅ `butler/cli/*_cli.py` |
| `inbound_pipeline` | ✅ `message_handler` 编排阶段列表化 |
| `env_defaults` Phase A–C | ✅ |
| `exp_cache` 锁 | ✅ RLock |
| `wechat_ilink` 结构拆分 | ✅ 子包 + ENG-5；ENG-13 条件触发见专文 |
| R1-3 core→gateway | ✅ `events_sink` + `test_core_events_sink_layering.py` |
| `delegate_phases` 按阶段拆包 | ✅ `delegate_phases/` 子包 + 125 行门面 |
| Owner UX P0–P6-A | ✅ 产品向，非本计划 |

---

## 2. 问题域（软件工程视角）

### A. 模块体量（God Module）

| 优先级 | 文件 | 行数 | 问题 |
|--------|------|------|------|
| **P0** | `butler/dev_engine/coding_knowledge.py` | 1613 | 定理/经验/管线；可接受但需子域边界 |
| **P1** | `butler/gateway/platforms/wechat_ilink/__init__.py` | ~1119 | **ENG-13** 条件触发；`phases` 已 ~370 行 |
| **P1** | `butler/core/agent_loop_phases.py` | 906 | turn 阶段编排；P0-A 已守门 |
| **P1** | `butler/gateway/locked_phases.py` | 826 | turn 终态 phase；ENG-11 注册表已首步 |
| **P1** | `butler/task_orchestrator.py` | 532 | ENG-4 done；图执行在 `dag_scheduler` |
| **P2** | `butler/orchestrator/` | ~590 | 门面 + `templates` / `loop_factory` 子模块 |
| **P2** | `butler/memory/facade.py` | 736 | 工具分发 + prefetch 同类 |
| — | `butler/tools/delegate_phases.py` | **125** | ✅ ENG-2 门面；勿重复立项 |

### B. 函数复杂度（>80 行，AST 扫描）

| 文件 | 函数 | 行数 | 建议 |
|------|------|------|------|
| `message_handler.py` | `_handle_message_after_pipeline` | 120 | 按「pipeline 后 / 锁内 / 出站」三段拆 |
| `message_handler.py` | `_handle_message_locked` | 111 | 与 `locked_phases` 对齐，减少双份逻辑 |
| `message_handler.py` | `_drain_queued_inbound` | 91 | 抽到 `inbound_drain.py` |
| `agent_loop_phases.py` | `_dispatch_tool_response` | 100 | 工具批次子状态机独立模块 |
| `delegate_phases.py` | `_init_dev_engine_state` | 137 | DevEngine 初始化工厂 |
| `task_orchestrator.py` | `execute_graph` | 182 | `DagScheduler` 类 |
| `task_orchestrator.py` | `spawn_agent` | 135 | `SubLoopBuilder` |

**团队约定（新增）**：生产代码单函数 **≤80 行**；超过须 PR 说明或拆 phase。

### C. 分层 / 依赖（R1 收口）

| ID | 现象 | 影响 | 状态 |
|----|------|------|------|
| R1-3 | `core/*` → `gateway.*` | Loop 单测需 mock gateway | **done** — `butler/core/events_sink.py` + `tests/test_core_events_sink_layering.py`；`core/` 无 `from butler.gateway` |
| R1-1 | `transport` → `core.streaming_tools` | Provider 切换测试重 | **streaming_signal** ✅ |
| R1-10 | `tools/*` → `gateway.*` | CLI 工具测试污染 | **contracts + execution_context** ✅ |
| R1-16 | `config.load_dotenv` | 测试 env 耦合 | **import 不触发 dotenv** ✅ |
| R1-18 | **~3356** 延迟 import | 环靠 lazy 维持 | **预算守门 3400** ✅ |

**目标架构**：

```text
butler/contracts/     # Protocol only（EventsSink, OutboundBridge, OwnerGate）
butler/core/          # 只依赖 contracts + transport + tools/registry 接口
butler/gateway/       # 实现 contracts，装配 inbound_pipeline
butler/tools/         # 通过 execution_context 查 gateway 能力，不直接 import
```

### D. 静默失败（R2 高价值）

| 位置 | 风险 | 产品化修复 |
|------|------|------------|
| `memory/semantic_index.py` | FTS fallback 不告知模型 | `recall_degraded` → `/诊断` + health |
| `memory/embedding.py` | HashingEmbedder 静默 | 启动 error + doctor 一行 |
| `skills/consolidator.py` | merge fallback 无标志 | 返回 `fallback_used` |

### E. 测试工程（PROD-P6-06）

| 项 | 现状 | 目标 |
|----|------|------|
| 全量 pytest | ~~101 fail~~ **0 fail**（2026-06-27） | ≤10 或 CI 永不跑全量 |
| 根因 | `test_tools_registry` 跨测状态 + `.env` 泄漏 | bisect 清单在 `pilot-log` |
| 隔离 | `MEMORY_AUTO_APPROVE=correction` 致单测失败 | `monkeypatch` / session fixture |
| 守门 | fast-gate + domain gate | 保持为发版 SSOT |

### F. 配置 / 模型（PROD-P6-07 ✅）

`get_model_config` 已走 `resolve_effective_model`；`model_context` 直调 resolve；`model_resolve` 统一 re-export auxiliary/embedding；静态守门见 `test_model_config_single_resolver.py`。

遗留（非阻塞）：

- `/model save` 读写 L2 不对称（文档已记）
- P1-2 fallback「默认不 auto 追加」为可选行为变更，见 maintainability §5

### G. 条件触发工程债（非发版门槛）

> **原则**：有明确触发再做；SSOT 分文档，勿并入 ENG 主立项重复排期。

| ID | 名称 | 触发 | SSOT |
|----|------|------|------|
| **ENG-13** | `wechat_ilink/__init__.py` 第三轮薄化 | 改 iLink/出站/登录 或 `__init__.py` 难维护 | [`wechat-ilink-round3-2026-06.md`](wechat-ilink-round3-2026-06.md) |
| **—** | `tool_batch.py` 辅助状态外提 | 动 tool 并行/护栏/两阶段逻辑时顺带 | 本文 §2.B；`process_tool_calls` 已 ~171 行 |
| **D7–D9** | PIM 加密 / 识图 P3 / terminal 白名单 | 产品/合规/剖面诉求 | [`post-consolidation-roadmap` §轨道 D](post-consolidation-roadmap-2026-05.md) |

---

## 3. 立项表（ENG 线）

| ID | 名称 | 批次 | 周期 | 依赖 |
|----|------|------|------|------|
| **ENG-1** | 复杂度预算 + 热点度量脚本 | 基线 | 3d | — |
| **ENG-2** | `delegate_phases` 按阶段拆包 | A | 1–2w | ENG-1 | **done** |
| **ENG-3** | `message_handler` 后段再薄化 | A | 1w | inbound_pipeline |
| **ENG-4** | `task_orchestrator` 图执行拆分 | A | 1w | — |
| **ENG-5** | `wechat_ilink/phases` 第二轮拆分 | B | 1–2w | — |
| **ENG-6** | `butler/contracts/` + EventsSink | B | 2–3w | ENG-2 可选 |
| **ENG-7** | tools→gateway 经 execution_context | B | 2w | ENG-6 |
| **ENG-8** | 记忆/embedding 降级显性化 | C | 1w | — |
| **ENG-9** | pytest 泄漏修债（逐模块） | C | 2–4w | 叙事 done |
| **ENG-10** | `model_defaults` 收口剩余硬编码 | C | 1w | — |
| **ENG-11** | `locked_phases` → phase 注册表 | D | 1–2w | ENG-3 |
| **ENG-12** | `orchestrator` 子系统门面 | D | 2w | ENG-6 | **done** |
| **ENG-13** | `wechat_ilink/__init__` 第三轮 | 条件 | 1–2w | ENG-5 | **backlog**（见专文） |

**不做（否决延续）**：`coding_knowledge` 全量重写、Loop 换框架、无测试的大重构。

---

## 4. 批次与执行顺序

```text
并行 G1-04 运营（每周 butler-ops-cadence.sh --weekly）

第 1 批（ENG-1，3 天）
  scripts/butler-complexity-report.sh  # 行数 + ≥80 行函数 + lazy import 计数
  CONTRIBUTING 增「单函数 ≤80 行」

第 2 批（ENG-2～4，3–4 周，可拆 PR）
  delegate_phases → delegate/{prepare,run,dev_engine,finalize}.py
  message_handler 后段 → gateway/turn_finalize.py
  task_orchestrator → dag_scheduler.py + subloop_builder.py
  守门：butler-owner-ux-p5-gate + butler-wechat-core-sim + fast-gate

第 3 批（ENG-5～7，与发版穿插）
  wechat_ilink/phases 按 connect/poll/send 拆
  contracts/ + 1 条 core→gateway 解耦竖切（建议从 compaction events 开始）

第 4 批（ENG-8～10，工程债）
  R2 降级标志 + /诊断
  pytest 按域修（gateway → tools → memory）
  model_defaults 剩余项

第 5 批（ENG-11～12，07-31 后或低风险窗）
  locked_phases 注册表
  orchestrator 门面（可选）
```

---

## 5. 分项验收标准

### ENG-2 · delegate_phases 拆分

1. 无单文件 >600 行（`delegate_phases.py` 变 re-export 薄层或删除）  
2. 单函数 ≤80 行（`_init_dev_engine_state` 拆工厂）  
3. `bash scripts/butler-pilot-dev-testing.sh` + `butler-wechat-dev-delegate-sim.sh` PASS  
4. `delegate_impl` 公共 API 不变  

### ENG-3 · message_handler 薄化

1. `message_handler.py` <550 行  
2. `_handle_message_locked` <60 行（编排-only）  
3. `tests/test_gateway_handler.py` + `butler-wechat-core-sim.sh` PASS  

### ENG-6 · contracts 竖切

1. 新增 `butler/contracts/events.py`（`EventsSink` Protocol）  
2. `context_compressor` / `compaction_task` **无** `from butler.gateway`  
3. gateway 在 `runner.py` 注册实现  
4. 相关 core 单测无需 import gateway  

### ENG-9 · pytest 修债

1. 全量 fail ≤10（或 maintainer optional 文档化不变）  
2. `test_tools_registry` 隔离（fixture autouse 重置 registry）  
3. 域 gate 仍绿  

---

## 6. 守门矩阵（每批 PR）

| 层级 | 命令 |
|------|------|
| PR 快扫 | `bash scripts/butler-pytest-fast-gate.sh` |
| Gateway | `bash scripts/butler-domain-pytest.sh gateway` |
| Core/委派 | `tests/test_premise_t8_delegate_separation.py` · dev delegate sim |
| 微信行为 | `bash scripts/butler-wechat-core-sim.sh` |
| CC 线束 | `./scripts/butler-cc-harness-gate.sh`（动 context 时） |
| 发版 | `bash scripts/butler-ops-cadence.sh --release` |

---

## 7. 风险与原则

1. **行为不变优先**：先 extract module，后改逻辑；每 PR 可回滚。  
2. **不与 G1-04 抢窗**：07-31 前不做 ENG-11/12 级大动。  
3. **延迟 import 禁止恶化**：拆模块时优先 **依赖倒置**，禁止新增 `core→gateway` 顶层 import。  
4. **审计 SSOT**：修完 R1-xx 在 `project-deep-audit-2026-06-r1to8.md` 标 ✅，勿另起表格。  
5. **产品边界**：[`roadmap-backlog` §1](roadmap-backlog-and-boundaries-2026-05.md) 否决项不适用本计划「优化」名义复活。

---

## 8. 建议首周动作（可立即开工）

| # | 动作 | 产出 |
|---|------|------|
| 1 | 实现 `scripts/butler-complexity-report.sh` | CI 可选 artifact |
| 2 | PR：拆 `delegate_phases._init_dev_engine_state` → `dev_engine/delegate_init.py` | ENG-2 首 PR |
| 3 | PR：`test_tools_registry` session 级 reset fixture | ENG-9 首 PR |
| 4 | 文档：`/诊断` 增 `embedding_degraded` / `recall_degraded` 设计草图 | ENG-8 前置 |

---

## 9. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-06-26 | 初版：基线度量 + ENG-1～12 立项 + 批次与验收 |
| 2026-06-26 | **ENG-1** `butler-complexity-report.sh` · **ENG-2** `delegate_init.py` · **ENG-9** registry fixture |
| 2026-06-26 | **ENG-2** `delegate_workspace` + `delegate_finalize`；**ENG-3** `turn_post_pipeline`（handler 672→574） |
| 2026-06-26 | **ENG-2 done**：`delegate_run_state/prepare/subagent/record/run/report`；`delegate_phases` 901→125 行 |
| 2026-06-26 | **ENG-8** 首步：`/诊断` 简要增记忆降级一行（嵌入/FTS/离线） |
| 2026-06-26 | **P0-B** `degradation_registry` + doctor/诊断；**P0-A** `safe_best_effort` + `tool_batch` 首步 |
| 2026-06-26 | **P1-C** `tool_dispatch` + `tool_batch_hooks`；**P0-A 续** locked/agent_loop phases |
| 2026-06-27 | **P0-A done**：`best_effort` 最近跳过 ring + `/诊断` 明细；三热点 `except Exception` 降 ~40%+ |
| 2026-06-29 | **P0-A 守门**：`butler-p0a-exception-gate.sh` + `agent_loop._record_skipped_plugin` 接 `best_effort_skip` 指标 |
| 2026-06-29 | **P0-B 守门**：per-component `degradation_active` gauge + `/诊断` since 明细 + `butler-p0b-degradation-gate.sh` |
| 2026-06-29 | **P1-C 续**：`context_compress_pipeline` + `tool_batch_finalize` + `llm_retry_outcomes` + `butler-p1c-gate.sh` |
| 2026-06-27 | **P1-C done**：`llm_retry_helpers` + `context_compress_support` |
| 2026-06-27 | **P1-D done**：`contracts/events` + `EventsSink` `@runtime_checkable` + gateway 注册 |
| 2026-06-27 | **P2-E**：`conftest` session env 默认 + sprint11/registry/sprint23 修债 |
| 2026-06-27 | **P2-F**：`pyproject.toml` mypy strict on `butler/contracts` + `delegate_run_state` |
| 2026-06-27 | **P2-G**：文档 9 处矛盾修正（architecture / DOCUMENTATION / roadmap 等） |
| 2026-06-27 | **ENG-6 续**：`GatewayEventsSink` 实现 contracts + 统一双注册表 |
| 2026-06-27 | **ENG-8 续**：Skill merge fallback → `degradation_registry` |
| 2026-06-27 | **ENG-9 done**：全量 pytest 0 fail（6250 pass） |
| 2026-06-27 | **ENG-7 首步**：`core/approval_cards`；tools/core 去 gateway import |
| 2026-06-27 | **ENG-8 续**：MCP warm-up → `sync_mcp_degradations_at_startup` |
| 2026-06-27 | **ENG-13 首步**：`health_report` 可选诊断块 → `safe_best_effort` |
| 2026-06-27 | **ENG-3 续**：`inbound_drain.py`；`message_handler` 500 行 |
| 2026-06-27 | **ENG-14 续**：mypy strict on `approval_cards` + `terminal_approval` |
| 2026-06-27 | **ENG-4 首步**：`dag_scheduler.py`；`execute_graph` 依赖 helper 迁出 |
| 2026-06-27 | **ENG-5 首步**：`connect_phases.py`；connect 子阶段从 `phases` 迁出 |
| 2026-06-27 | **ENG-7 续**：`network_route_verify_runner` 入 gateway；tools 去 handler wrapper |
| 2026-06-27 | **ENG-6 续**：contracts 双 Protocol 说明 + gateway sink 契约测试 |
| 2026-06-27 | **ENG-13 续**：langfuse trace 创建/flush/shutdown → `safe_best_effort` |
| 2026-06-27 | **ENG-5 续**：`poll_phases.py` + `send_phases.py`；`phases` 639 行 |
| 2026-06-27 | **ENG-4 续**：`prepare_layer_node` / router / batch helper 入 `dag_scheduler` |
| 2026-06-27 | **ENG-13 done**：langfuse 全路径 `_lf_void` / `_lf_best_effort` |
| 2026-06-27 | **ENG-14 续**：mypy strict on `dag_scheduler` + `network_route_verify_runner` |
| 2026-06-27 | **ENG-5 done**：`qr_phases.py`；`phases` 门面 ~370 行 |
| 2026-06-27 | **ENG-4 done**：`workflow_step_runner`（retry/rescue）；`task_orchestrator` 532 行 |
| 2026-06-27 | **ENG-14 done**：`butler-mypy-strict-gate.sh` 入 fast-gate |
| 2026-06-27 | **ENG-6 续**：contracts 测试覆盖 gateway→transcript 写入路径 |
| 2026-06-27 | **ENG-3 done**：`locked_turn_orchestrator` + `handler_commands`；handler 332 行 |
| 2026-06-27 | **ENG-7 done**：tools/core 全量 AST 分层守门 + execution_context 唯一 seam |
| 2026-06-27 | **ENG-8 done**：`refresh_degradations_for_owner_brief` + live MCP 并入简要 /诊断 |
| 2026-06-27 | **ENG-11 首步**：`locked_phase_registry.py`；orchestrator 注册表驱动 |
| 2026-06-27 | **ENG-10 首步**：embedding/provider 字面量收口 `model_defaults` + 静态守门 |
| 2026-06-27 | **ENG-9 续**：`butler-eng-domain-gate.sh`（gateway/memory/tools 子集） |
| 2026-06-27 | **ENG-11 done**：pre-lock / in-context 双段 phase 注册表 + 测试 |
| 2026-06-27 | **ENG-10 done**：vision/presets 收口 + 扩展字面量守门 |
| 2026-06-27 | **ENG-12 首步**：`butler/orchestrator/` 包；`templates` + `loop_factory` |
| 2026-06-29 | **R1 续收尾**：OwnerGate/BridgeAccess registry；**llm_retry** 拆 `invoke/errors/success/safe` |
| 2026-06-29 | **R1-16/R1-18**：config import 不 load dotenv 单测；lazy import 预算守门 3400 |
| 2026-06-29 | **P6-05/06**：PMF report 单测；P6-06 收束为 ENG-9 |
| 2026-06-29 | **B1 done**：`butler-wechat-dual-playbook-probe.sh` |
| 2026-06-29 | **R1-3 done**（文档收口）；**ENG-13** 条件触发专文 `wechat-ilink-round3-2026-06.md` |
| 2026-06-29 | **P2-G 续**：`project-optimization` S1–S3/§四 与 P0-A/B、P1-C 对齐；`butler-p2g-doc-gate.sh` |
| 2026-06-30 | **P1-D 验收** + **P2-E 收口**：`project-optimization` / `agent-testing-strategy` / bisect 记录对齐 `4d064b9` |
| 2026-06-30 | **P2-F 扩面**：mypy strict **37** 模块（contracts 全包 + P1-C core seams）；`butler-mypy-strict-gate.sh` |
