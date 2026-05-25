# 外部项目学习规划（Butler v4）

> **状态**：P0–P2 已落地（2026-05-25，零依赖）  
> **触发**：[`reference/待学习项目.md`](../../reference/待学习项目.md) 泛清单筛选 + Butler 现状对照  
> **原则**：**只借鉴设计、零新增依赖**（不引入 `prometheus-client`、消息中间件客户端、Dify/OpenClaw 运行时）；在现有 Python 标准库 + Butler 模块内落地。  
> **主学习线**：Claude Code（[`cc-butler-gap-analysis-2026-05.md`](cc-butler-gap-analysis-2026-05.md)）  
> **本地代码**：`reference/learn-*` 仅作阅读对照（**gitignore**）

---

## 1. 学习目标与边界

| 维度 | Butler 现状 | 学习目的 |
|------|-------------|----------|
| 产品形态 | 微信管家 + 自建 Loop + 多项目 | 不变成 K8s 平台、不嵌 Dify/OpenClaw 运行时 |
| 可观测性 | `/诊断` 文本 + 内存计数器（`completion_telemetry`、`hooks/telemetry`） | 借鉴 **Prometheus 指标模型**（命名/类型/标签），统一到 **零依赖** 运行时快照，强化 `/诊断` 与 health |
| 入站队列 | `message_queue.py`：now/next/later + 2s 去重 | 对齐 **steer/followup/collect/interrupt** 语义与 cap/drop |
| Agent 平台 | 已对标 Claude Code P0–P4 | **OpenClaw** 作第二对照（Gateway/会话/队列/多通道） |
| 工作流产品化 | 无可视化工作流 | **Dify** 仅学权限与 Graph 编排，**二期可选** |

**明确不做（本规划周期）**：任何 **pip 新依赖**；Istio/K8s 联邦；RocketMQ/Kafka 集群；OpenClaw/Dify 子进程或嵌入运行时。

---

## 2. 本地参考代码索引

| 目录 | 上游 | 克隆方式 | 建议阅读路径 |
|------|------|----------|--------------|
| `reference/learn-prometheus-client/` | [prometheus/client_python](https://github.com/prometheus/client_python) | 浅克隆 full | `prometheus_client/` 中 Counter/Histogram/Gauge；`README` |
| `reference/learn-dify/` | [langgenius/dify](https://github.com/langgenius/dify) | sparse：`api/`、`api/core/` | `api/core/workflow/workflow_entry.py`（GraphEngine）；权限相关 `api/services` |
| `reference/learn-openclaw/` | [openclaw/openclaw](https://github.com/openclaw/openclaw) | sparse：`docs/`、`packages/`、`src/` | `docs/concepts/queue.md`；`src/gateway/session-*.ts`；`src/sessions/` |

**未克隆（体积/收益）**：

- **Apache Kafka / RocketMQ**：仅文档级学习（见 §4.2）；需要时再 `sparse` 克隆 `rocketmq-client-python` 或官方 design doc。
- **Prometheus Server / Grafana**：用官方 Docker compose 做联调即可，不必 vendoring 全仓。

更新克隆：

```bash
cd /home/ailearn/projects/WFXM/reference/learn-prometheus-client && git pull --depth 1
# 其余同理；OpenClaw 体积大，建议保持 sparse，勿 full clone
```

---

## 3. 三条学习线详细规划

### 3.1 可观测性 — Prometheus **设计思想**（零依赖，P0，1–2 周）

#### 借鉴什么（读 `learn-prometheus-client` 或官方文档即可）

- **指标类型**：Counter（只增）、Gauge（瞬时值）、Histogram（延迟分布 → 用固定长度环形缓冲算 p50/p95）
- **标签维度**：低基数（`provider`、`tool_name`、`outcome`），**禁止**完整 `session_key`
- **命名**：`butler_<子系统>_<度量>_<单位>`，与现有 health 字段一一可对照

#### Butler 现状（可复用，不拆散）

- `completion_telemetry.py`、`hooks/telemetry.py` — 已是 Counter 形态
- `health_report.py` + `message_handler` 写入的 `health` dict — 已是「每 session 快照」
- `LoopResult.diagnostics` — turn 级事件

#### 落地设计（**不** 新增 `prometheus-client`）

新增 **`butler/ops/runtime_metrics.py`**（仅 stdlib：`threading` + `collections` + `time`）：

| 内部结构 | 对外 API | 写入点 |
|----------|----------|--------|
| 全局 Counter 表 | `inc("llm_request", labels={...})` | `llm_retry.call_llm_with_retry` |
| 按工具 Counter | `inc("tool_call", tool=...)` | `tool_batch.process_tool_calls` |
| 延迟环形缓冲（如 64 条） | `observe_ms("turn_duration", ms)` | `agent_loop` 回合结束 |
| Gauge | `set("inbound_queue_depth", n)` | `message_queue.enqueue` / `pop` |
| 进程级汇总 | `snapshot_global() -> dict` | `/诊断` 追加一节「运行指标」 |

**合并策略**：`completion_telemetry` / `hooks/telemetry` **保留 API**，内部改为调用 `runtime_metrics.inc`，避免双份逻辑。

#### 实施阶段

| 阶段 | 交付 | 依赖 |
|------|------|------|
| **L1** | `runtime_metrics.py` + `format_metrics_diagnostic_lines()` | 无 |
| **L2** | 在 loop / gateway 埋点；`/诊断` 输出 8–12 行汇总 | 无 |
| **L3** | `docs/ops/diagnostic-thresholds.md`：阈值说明（如 LLM 失败率 >10% 查模型） | 无 |

**刻意不做**：HTTP `/metrics`、Grafana JSON、Prometheus Server 联调（运维若需要，可日后用日志解析或再加依赖，不在本约束内）。

#### 验收

- `/诊断` 含全局 + 当前 session 指标，与改造前 completion 计数一致
- `pytest tests/test_runtime_metrics.py`（新）覆盖 inc/observe/snapshot
- 无 `requirements.txt` / `pyproject` 变更

---

### 3.2 消息队列语义 — OpenClaw + MQ 思想（P1，2–3 周）

#### Butler 现状

```text
message_queue: now > next > later，内存 deque，2s 去重，turn 活跃时入队
/steer: 注入当前 run（已有 wechat-steer 文档）
drain: message_handler 回合结束拼回主回复
```

#### OpenClaw 对照（`reference/learn-openclaw/docs/concepts/queue.md`）

| OpenClaw 模式 | 语义 | Butler 映射建议 |
|---------------|------|-----------------|
| `steer` | 同 turn 注入活跃 runtime | 已有 `/steer`；需明确与「队列 next」优先级 |
| `followup` | 当前 run 结束后单独 turn | ≈ 当前 `enqueue` + drain |
| `collect` | debounce 合并为一条 followup | **新增**：`BUTLER_QUEUE_COLLECT_MS` + 合并摘要 |
| `interrupt` | 中止当前 run，跑最新 | **新增**：与 `run_interruptible` 集成 |
| `cap` / `drop` | 20 条 + summarize/old/new | **新增**：对齐 `max_queue_depth` + 溢出策略 |
| Lane | session 串行 + global 并发上限 | 映射 `session_registry` + 全局 semaphore |

#### Kafka/RocketMQ（不引集群，只学语义）

| 概念 | 用于 Butler 的设计决策 |
|------|-------------------------|
| 分区键 = session_key | 多实例 Gateway 时保证同会话有序 |
| 消费组 | 单 consumer  per partition → 与「每 session 单 active run」一致 |
| at-least-once + 幂等 | 入站 dedupe + push_queue 已有方向；需 message_id |
| 背压 | 队列 cap + drop summarize → 用户可见「仍在处理」 |

#### 实施阶段（均在 `message_queue.py` + `message_handler.py`，零依赖）

| 阶段 | 交付 |
|------|------|
| **L1** ✅ | `BUTLER_GATEWAY_QUEUE_MODE`、`CAP`、`DROP`；`/queue` 会话覆盖（`butler/gateway/queue_settings.py`） |
| **L2** ✅ | `collect`：`pop_all_merged` 合并 drain；溢出 `summarize` 摘要 |
| **L3** ✅ | `interrupt`：`loop.interrupt()`；`steer` 模式走 `/steer` 同路径 |
| **L4** | ~~jsonl 持久化~~ **暂缓**（见 D5）；当前仅 transcript 审计 |
| **L5（远期）** | 多实例 MQ **暂缓**（见 D7） |

#### 必读 OpenClaw 文件

- `docs/concepts/queue.md`、`docs/concepts/queue-steering.md`
- `src/gateway/session-utils.ts`、`session-reset-service.ts`（会话边界）
- `src/gateway/server/ws-connection/message-handler.ts`（入站管线）

#### 验收

- 语料/集成测：cap 溢出、collect 合并、interrupt 中止
- 与 CONTRIBUTING H11（入站队列第二条）可勾选

---

### 3.3 Gateway 与会话 — OpenClaw 设计（P1–P2，零依赖）

**优先读**：`learn-openclaw/docs/concepts/queue.md`、`queue-steering.md`（不必读 TS 实现细节）。

| OpenClaw 设计 | Butler 落地（现有模块） |
|---------------|-------------------------|
| per-session 串行 + 全局并发上限 | `session_registry`：`max_sessions` +「每 session 仅一个 active turn」文档化 |
| session transcript 事件流 | 扩展 `session_transcript.py` 事件名（queue_drop、turn_interrupt） |
| `/queue` 会话级覆盖 | `message_handler` 增加 `/queue steer\|followup\|collect\|interrupt` 与 per-session 存储（`.butler/` json） |
| typing + 单条 ack | `outbound_bridge.py` 已有；补齐 `delegate_role` 在 `start_turn` **之后** 再设（测试已修） |
| steer vs followup 边界 | 与 `/steer`、P3 `message_queue` 文档统一（`docs/guides/wechat-core-scenario.md`） |

### 3.4 编排与权限 — Dify **设计**（P2 可选，零依赖）

**只读** `learn-dify/api/core/workflow/workflow_entry.py` 理解：**图节点、失败即事件、子图**。

| Dify 概念 | Butler 映射（不引入 GraphEngine） |
|-----------|-----------------------------------|
| Workflow DAG | 现有 `task_orchestrator.py` + `delegate_task` |
| 节点失败策略 | `LoopResult` / `AgentReport` 增加 `step_failed` 摘要字段 |
| Human-in-the-loop | 微信回复「确认/取消」→ `permissions.py` + 临时 gate（环境变量已有 plan mode） |
| 步骤级工具白名单 | 扩展 `permissions.yaml`：`workflow_steps.<id>.tools` |

**不做**：Dify API、RAG pipeline、可视化编辑器。

---

## 4. 优先级与里程碑

| 优先级 | 借鉴源 | 里程碑（零依赖） | 测试 |
|--------|--------|------------------|------|
| **P0** | Prometheus **模型** | `runtime_metrics` + `/诊断` 增强 | `test_runtime_metrics.py` |
| **P1** | OpenClaw **queue** | cap / drop / collect / `/queue` 命令 | `test_message_queue.py` 扩展 |
| **P1b** | OpenClaw **session** | transcript 事件 + registry 文档 | `test_cc_p3_p4` transcript |
| **P2** ✅ | Dify **DAG 思想** | `workflow_steps` 白名单、`human_gate` 确认、`AgentReport.step_outcomes` | `test_p2_workflow_permissions.py` |

---

## 5. 与现有路线图关系

| 已有计划 | 关系 |
|----------|------|
| `cc-butler-gap-analysis` §11 P3/P4 | **已完成**；本规划是 **运维/规模化** 补充，不重复 CC 线束 |
| `post-consolidation-roadmap` D0c `/steer` | P1 队列线直接扩展 |
| `memory-unification` | 无冲突；metrics 可加 memory_sync 结果标签 |
| Hermes `reference/hermes-agent` | 与 OpenClaw 并列对照；**优先 OpenClaw**（Gateway 更贴近 Butler） |

---

## 6. 阅读作业（建议顺序）

### 第 1 周（可观测性，零依赖）

1. 阅读 Prometheus 文档「指标类型」一节（或 `learn-prometheus-client` 源码结构，**不 import**）
2. 实现 `butler/ops/runtime_metrics.py` 草案
3. 合并 `completion_telemetry` → 统一 inc API

### 第 2 周（队列）

1. `reference/learn-openclaw/docs/concepts/queue.md`（全文）
2. Butler：`message_queue.py`、`message_handler.py`（drain/follow）
3. 写 ADR：`docs/plans/adr-gateway-queue-modes.md`（可选）

### 第 3 周（OpenClaw Gateway）

1. `learn-openclaw/src/gateway/session-utils.ts`（选读 200 行/函数级）
2. 对比 `session_transcript.py`、`session_registry.py`
3. 更新 `v4-architecture.md` Gateway 小节（若实现 L1）

### 第 4 周（Dify，可选）

1. `learn-dify/api/core/workflow/workflow_entry.py`
2. 评估：是否将 `TaskOrchestrator` 暴露为微信可触发的「工作流」命令

---

## 7. 决策记录（已按「零依赖」收敛）

| # | 问题 | 结论 |
|---|------|------|
| D1 | 是否引入 `prometheus-client`？ | **否**；只用其指标命名与类型思维 |
| D2 | 队列 persist 是否 L1 必做？ | **否**；L1 仅 cap/drop/mode |
| D3 | 是否对接 RocketMQ/Kafka？ | **否**（本阶段）；语义借鉴即可 |
| D4 | 是否嵌入 Dify/OpenClaw？ | **否**；只改 Butler 自有模块 |
| D5 | L4 入站队列 jsonl 持久化？ | **暂缓**（2026-05-25）；无重启丢队列事故前不做 |
| D6 | 确认后自动续跑 workflow？ | **暂缓**；维持「确认 → 再发 /workflow」 |
| D7 | L5 多实例 MQ？ | **暂缓**；水平扩展 Gateway 时另立项 |

---

## 8. 建议实施顺序（可直接开干）

1. **P0**：`runtime_metrics.py` + `/诊断` 一节 + 合并 telemetry（约 300–500 行）
2. **P1**：`message_queue` cap/drop/collect + `/queue` 斜杠命令（约 400 行 + 测试）
3. **P1b**：`session_transcript` 事件对齐 OpenClaw 命名（小改）
4. **P2**：`permissions.yaml` 步骤级工具 + TaskOrchestrator 失败摘要（按需）

---

## 9. 与「引依赖」方案差异（备忘）

| 原规划 | 零依赖替代 |
|--------|------------|
| `prometheus-client` + `/metrics` HTTP | `runtime_metrics` + `/诊断` 文本快照 |
| Grafana 仪表盘 | `diagnostic-thresholds.md` + 微信 `/诊断` |
| Redis/RocketMQ 队列 | 内存 deque + cap/drop + transcript/jsonl 持久化 |
| Dify GraphEngine | `task_orchestrator` + YAML DAG |

---

*克隆时间：2026-05-25。OpenClaw/Dify 体量大，请勿 full clone；需要更多路径时用 `git sparse-checkout add` 扩展。*
