---
name: research-program
description: 研究模式须读 PROGRAM.md、harness 只读、experiments 可写、METRIC 记账
triggers:
  - 实验
  - experiment
  - harness
  - metric
  - keep
  - discard
  - 研究
version: 1
---

# research-program

1. **先读** 项目根 `PROGRAM.md`（若存在）与 `.butler/harness/` 入口说明。
2. **勿改** `.butler/harness/`；`BUTLER_EXPERIMENT_MODE=1` 时仅写 `experiments/`。
3. **跑评测**：`run_runtime_job` / `butler runtime run harness-eval`；从 stdout 解析 `METRIC name=value`。
4. **记账**：失败记 `crash`；改善记 `keep`；回退记 `discard`（CLI `butler experiment`）。
5. **简洁性**：同等指标选更简单 diff；连续 crash 先停改假设。
