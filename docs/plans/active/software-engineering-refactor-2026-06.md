# 软件工程整理计划（复杂度 · 分层 · 测试）

> **状态**：立项 **2026-06-26**  
> **性质**：纯工程（**不**改产品边界；与 G1-04 观测窗 **并行**）  
> **登记**：[`roadmap-backlog`](../decisions/roadmap-backlog-and-boundaries-2026-05.md) §3.11（待写入）  
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

## 1. 当前基线（2026-06-26 命令验证）

| 指标 | 数值 | 说明 |
|------|------|------|
| `butler/` Python 文件 | ~453 | 与 06 审计同量级 |
| **>800 行** 单文件 | **2** | `coding_knowledge.py` 1613、`delegate_phases.py` 1244 |
| **>600 行** 单文件 | **~15** | 含 `wechat_ilink/phases.py` 1205、`message_handler` 672 |
| `main.py` | **177** | ✅ R1-7 已薄化（原 1340） |
| `delegate_impl.py` | **385** | ✅ R1-5 已拆出 `delegate_phases` |
| `wechat_ilink` | **子包** | ✅ PROD-P2-01；`phases.py` 仍 1205 行 |
| 延迟 `from butler.` | **~2454** | 环靠 lazy import 维持 |
| `core/` → `gateway/` 顶层 import | **1 文件** | 较审计改善，未归零 |
| 全量 `pytest tests/` | **~101 fail** | 泄漏 + `.env` 耦合；发版 gate 绿 |
| `get_model_config` | 已委托 `resolve_effective_model` | P0-1 部分完成 |

### 1.1 已收口（勿重复立项）

| 项 | 状态 |
|----|------|
| `main.py` CLI 拆分 | ✅ `butler/cli/*_cli.py` |
| `inbound_pipeline` | ✅ `message_handler` 编排阶段列表化 |
| `env_defaults` Phase A–C | ✅ |
| `exp_cache` 锁 | ✅ RLock |
| `wechat_ilink` 结构拆分 | ✅ 子包（`phases` 仍大） |
| Owner UX P0–P6-A | ✅ 产品向，非本计划 |

---

## 2. 问题域（软件工程视角）

### A. 模块体量（God Module）

| 优先级 | 文件 | 行数 | 问题 |
|--------|------|------|------|
| **P0** | `butler/tools/delegate_phases.py` | 1244 | 委派全阶段塞单文件；`_init_dev_engine_state` 137 行 |
| **P0** | `butler/gateway/platforms/wechat_ilink/phases.py` | 1205 | P2-01 后仍超大；协议轮询+发送混合 |
| **P1** | `butler/dev_engine/coding_knowledge.py` | 1613 | 定理/经验/管线；可接受但需子域边界 |
| **P1** | `butler/gateway/locked_phases.py` | 775 | turn 终态 10+ phase 函数 |
| **P1** | `butler/task_orchestrator.py` | 798 | `execute_graph` 182 行、`spawn_agent` 135 行 |
| **P2** | `butler/orchestrator.py` | 856 | 门面仍兼 Skill/Memory/Loop 工厂 |
| **P2** | `butler/memory/facade.py` | 736 | 工具分发 + prefetch 同类 |

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

### C. 分层 / 依赖（R1 开放）

| ID | 现象 | 影响 |
|----|------|------|
| R1-3 | `core/*` 延迟 import `gateway.*`（compact/steer/queue） | Loop 单测需 mock gateway |
| R1-10 | `tools/*` → `gateway.outbound_bridge` / `owner_gate` | CLI 工具测试污染 |
| R1-1 | `transport` → `core.streaming_tools` | Provider 切换测试重 |
| R1-18 | **~2454** 延迟 import | 无 `butler/contracts/`；环靠 lazy 维持 |
| R1-16 | `config.load_dotenv` | R8-3 已入口化，需确认测试仍隔离 |

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
| 全量 pytest | ~101 fail | ≤10 或 CI 永不跑全量 |
| 根因 | `test_tools_registry` 跨测状态 + `.env` 泄漏 | bisect 清单在 `pilot-log` |
| 隔离 | `MEMORY_AUTO_APPROVE=correction` 致单测失败 | `monkeypatch` / session fixture |
| 守门 | fast-gate + domain gate | 保持为发版 SSOT |

### F. 配置 / 模型（PROD-P6-07 收窄）

`get_model_config` 已走 `resolve_effective_model`。剩余：

- embedding / gateway VLM 硬编码字面量 → `model_defaults.py`  
- `llm_fallback` auto 链 → yaml 可配  
- `/model save` 读写 L2 不对称（文档已记）

---

## 3. 立项表（ENG 线）

| ID | 名称 | 批次 | 周期 | 依赖 |
|----|------|------|------|------|
| **ENG-1** | 复杂度预算 + 热点度量脚本 | 基线 | 3d | — |
| **ENG-2** | `delegate_phases` 按阶段拆包 | A | 1–2w | ENG-1 |
| **ENG-3** | `message_handler` 后段再薄化 | A | 1w | inbound_pipeline |
| **ENG-4** | `task_orchestrator` 图执行拆分 | A | 1w | — |
| **ENG-5** | `wechat_ilink/phases` 第二轮拆分 | B | 1–2w | — |
| **ENG-6** | `butler/contracts/` + EventsSink | B | 2–3w | ENG-2 可选 |
| **ENG-7** | tools→gateway 经 execution_context | B | 2w | ENG-6 |
| **ENG-8** | 记忆/embedding 降级显性化 | C | 1w | — |
| **ENG-9** | pytest 泄漏修债（逐模块） | C | 2–4w | 叙事 done |
| **ENG-10** | `model_defaults` 收口剩余硬编码 | C | 1w | — |
| **ENG-11** | `locked_phases` → phase 注册表 | D | 1–2w | ENG-3 |
| **ENG-12** | `orchestrator` 子系统门面 | D | 2w | ENG-6 |

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
