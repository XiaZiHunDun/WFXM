# Agent 生产化条件项 ADR（AP-13–AP-16）

> **状态**：已登记 · **默认均不实现**  
> **关联**：[`agent-production-gap-2026-06.md`](../active/agent-production-gap-2026-06.md) · [`roadmap` §3.13](roadmap-backlog-and-boundaries-2026-05.md)

## AP-13 — 异步 HITL（Redis + `/resume`）

**触发**：合规要求释放计算资源；或多实例 gateway 共享挂起态。

**否决延续**：单进程微信管家、Owner 同步确认、`human_gate` 文件持久化已满足 T6。

**若立项**：Redis TTL checkpoint + 独立 resume API；**不得** `time.sleep` 占线程；需 ADR 修订 transcript 策略。

## AP-14 — workflow checkpoint 读回续跑

**触发**：长 DAG 重跑成本可观测且 Owner 确认接受「跳过已完成节点」。

**现状**：`workflow_runs/*-checkpoint.json` 只写不读（[`permission-gate-stack.md`](../../architecture/permission-gate-stack.md) §7.2）。

**若立项**：`workflows/runner.py` 读 checkpoint 跳过 `done` 步；与 `BUTLER_WORKFLOW_AUTO_RESUME` 矩阵文档化。

## AP-15 — OTLP 导出 StructuredEvent

**触发**：运维强制 OpenTelemetry；或 LangFuse 不足。

**现状**：`butler/core/structured_events.py` + `runtime_metrics` 进程内计数；LangFuse opt-in。

**若立项**：薄 OTLP bridge，**不** 引入重 APM 默认依赖；保持 opt-in。

## AP-16 — `terminal` argv 白名单（D9）

**触发**：post-consolidation 轨道 D 立项；或生产事故来自 shell 逃逸。

**现状**：`path_safety.prepare_shell_command` + profile/extra env；无细粒度 argv 表。

**若立项**：`.butler/terminal-allowlist.yaml` + ADR；与 `BUTLER_TERMINAL_PROFILE` 正交。
