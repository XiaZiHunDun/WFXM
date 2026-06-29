# Agent 生产化差距与落地（2026 H2）

> **状态**：AP-1–AP-12 **done**（2026-06）· AP-13–AP-16 **条件 ADR**  
> **规划原文**：Cursor plan `Agent 生产化差距规划`（不修改 plan 文件）  
> **登记**：[`roadmap` §3.13](../decisions/roadmap-backlog-and-boundaries-2026-05.md#313-agent-生产化ap-1162026-h2)

## 边界（不变）

- **不** LangGraph 替换 `agent_loop`
- **不** 默认全量 OTel/Grafana（S11 否决）
- **不** 默认 Redis 异步 HITL（微信同步门控为产品形态）
- transcript + 文件门控优先于 SQLite checkpoint

## 三铁律落地摘要

| 铁律 | Butler 交付 |
|------|-------------|
| 状态机 | `LoopTransitionReason` + [`agent-loop-state-machine.md`](../../architecture/agent-loop-state-machine.md)；workflow DAG 维持 |
| 可观测 | `structured_events` + `runtime_metrics_sink`；runbook §Agent 故障 10 分钟 |
| 轨迹 Eval | `tool_boundary_registry` + `butler-trajectory-compliance-gate.sh`（TCR） |

## 守门脚本

| 脚本 | 用途 |
|------|------|
| `scripts/butler-trajectory-compliance-gate.sh` | strict 语料 + 边界测试 → `.butler/reports/tcr-latest.json` |
| `scripts/butler-agent-eval-weekly.sh` | CuP/TCR/Pass@3 周报 |
| `scripts/butler-capability-baseline.sh` | read/delegate/workflow 三件套季度跑分 |
| `scripts/butler-pytest-fast-gate.sh` | 含 TCR warn-only |

## 运营节奏

| 频率 | 命令 | 产出 |
|------|------|------|
| 每周 | `bash scripts/butler-ops-cadence.sh --weekly` | G1-04 打卡 + `.butler/reports/agent-eval-weekly.json` |
| 每季 | `bash scripts/butler-ops-cadence.sh --quarterly` | 周报 + `.butler/reports/capability-baseline.json` |
| 发版 | `bash scripts/butler-ops-cadence.sh --release` | 周报 + P5/fast gate |

**TCR 升级**：`butler-pytest-fast-gate.sh` 内 TCR 暂 `--warn-only`；窗内周报稳定 **4 周后**（约 **2026-07-27**）改 `--strict`（98%）。

## 条件项（AP-13–16）

见 [`agent-production-conditional-adr-2026-06.md`](../decisions/agent-production-conditional-adr-2026-06.md)
