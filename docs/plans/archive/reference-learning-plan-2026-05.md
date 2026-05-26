# 外部项目学习规划（Butler v4）

> **状态**：P0–P2 **已落地并收口**（2026-05-25，零依赖）；**无后续必做项**  
> **验收索引**：[`../guides/external-reference-roadmap-2026-05.md`](../../guides/external-reference-roadmap-2026-05.md) · 阶段 A/B/C：[`../guides/phase-abc-external-reference.md`](../../guides/phase-abc-external-reference.md)  
> **主学习线**：Claude Code — [`cc-butler-gap-analysis-2026-05.md`](../active/cc-butler-gap-analysis-2026-05.md)  
> **本地代码**：`reference/learn-*`（**gitignore**，只读对照）

---

## 1. 边界（仍有效）

| 做 | 不做 |
|----|------|
| Prometheus **指标模型** → `runtime_metrics` + `/诊断` | `prometheus-client`、Grafana 必装 |
| OpenClaw **队列语义** → `message_queue` mode、`/queue` | jsonl WAL、多实例 MQ |
| Dify **DAG 思想** → `workflow_steps`、`human_gate` | 嵌入 Dify 运行时 |
| OpenClaw 第二对照（Gateway/会话） | 嵌入 OpenClaw 子进程 |

OpenClaw 详表：[`openclaw-learning-plan-2026-05.md`](../comparisons/openclaw-learning-plan-2026-05.md)。LangChain/Dify/Langflow 全量对照见各 `*-butler-comparison-2026-05.md`（**非待办**，见 [`roadmap-backlog-and-boundaries-2026-05.md`](../decisions/roadmap-backlog-and-boundaries-2026-05.md)）。

---

## 2. 已落地交付（速查）

| 线 | 交付 | 模块 / 文档 | 测试 |
|----|------|-------------|------|
| **P0** 可观测性 | Counter/Gauge/Histogram 快照 | `butler/ops/runtime_metrics.py`、[`diagnostic-thresholds.md`](../../ops/diagnostic-thresholds.md) | `test_runtime_metrics.py` |
| **P1** 入站队列 | followup/collect/interrupt/steer | `gateway/message_queue.py`、`queue_settings.py` | `test_message_queue.py` |
| **P1b** 会话 | transcript 事件、registry | `session_transcript`、gap §11 | `test_cc_p3_p4_features.py` |
| **P2** 工作流 | 步骤白名单、人工确认 | `human_gate`、`workflow_steps` | `test_p2_workflow_permissions.py` |
| **阶段 A/B/C** | Hermes/LC/Dify/LF 子集 | 见 phase-abc | `test_phase_a/b/c_external.py` |

---

## 3. 决策记录（零依赖）

| # | 结论 |
|---|------|
| D1 | 不引入 `prometheus-client` |
| D2 | 入站队列不做 jsonl 持久化 |
| D3 | 不对接 RocketMQ/Kafka |
| D4 | 不嵌入 Dify/OpenClaw 运行时 |
| D5 | workflow 确认后不自动续跑 |

defer 与补做：[`../guides/external-reference-deferred-2026-05.md`](../../guides/external-reference-deferred-2026-05.md)。

---

## 4. 与其它规划关系

| 文档 | 关系 |
|------|------|
| `cc-butler-gap-analysis` | Loop 线束已完成；本规划为运维/规模化补充 |
| `post-consolidation-roadmap` | 产品运营正交 |
| `memory-unification` | 无冲突 |

---

## 5. 本地参考克隆（可选）

```bash
# reference/learn-prometheus-client、learn-dify、learn-openclaw — 主公维护，sparse clone
```

*2026-05-25 收口。原 §3–§7 实施设计叙述已省略；实现以代码与 phase-abc 验收表为准。*
