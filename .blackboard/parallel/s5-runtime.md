# S5 — runtime 会话（运行引擎/能力边界）

**职责**：负责 `packages/runtime/**`——run engine（主循环编排）、capability boundary、grant/approval 决策、Run Trigger 归一、跟 side-effect 咽喉相关的落库协调。

## 独占路径

- `packages/runtime/**`

## 边界（不可动）

- 消费 `domain` +（视现状）`ports`，不反向 import `apps / cli`。
- 若 runtime 当前直接 import persistence 的 store——需持久化能力时优先走端口/经注入，不写死到某 adapter 实现。新增对其它包的公共依赖变更 → 提 PR 由 S1 落 `package.json`。
- 不改 ports barrel / DESIGN.md / state.md / arch guard 全局文件。
- 涉及 grant/审批/approval 逻辑的语义（Policy → wait_approval → ScopedGrant → Provider Boundary → Audit 链）守住 DESIGN §3 事实规则，改动前重读 `DESIGN.md`。

## 依赖/上游

- 依赖 S2（domain 契约）、S3（ports 端口，如 Repository Port）、S4（persistence store）。是 S6（apps/api）的主消费对象。

## 常规先手

- 主循环/重试/queue/compaction 改动跑 `packages/runtime` + 相应 harness 测试（`tests/` 相关）。
- 新增副作用必经副作用咽喉（Policy→…→Audit）；模型调用不走咽喉（D-series 事实规则）。

## 最小门禁（提交前）

```bash
cd butler-v5/packages/runtime && pnpm exec tsc --noEmit
cd butler-v5 && CI= pnpm exec vitest run packages/runtime -q
pnpm exec eslint packages/runtime --ext .ts --max-warnings 0
# 涉及 gateway/queue/workflow 时加：
CI= pnpm exec vitest run tests/gateway tests/test_p2_workflow_permissions.py-tests 2>/dev/null || true
```

> 注：部分历史 harness 编号来自 v4 脚本；以现有 `tests/` 实际文件为准。

## 当前相关待办

- D47 候选：exec 记账若落在引擎层，则与 S6 协同；MemoryService 物化（§12）横跨本会话 + S3/S6，由 S1 领衔先排清单再见分晓。