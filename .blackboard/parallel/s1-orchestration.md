# S1 — 编排/集成会话（唯一在 main 的会话）

**职责**：并行开发的交警 + 唯一解开共享/承重文件冲突者。维护黑板、端口目录、全局 arch guard；把关全量 5-gate；把各 `par/<area>` 分支合回 main。

## 独占路径（只有 S1 可提交）

- `.blackboard/**`（state.md、shifts/、parallel/）
- `butler-v5/DESIGN.md`
- `butler-v5/packages/ports/port-catalog.md`
- `butler-v5/packages/ports/src/index.ts`（thin barrel）
- 各包 `package.json` 的 `exports` / `dependencies` 跨包变更的**终审**（子会话提议，S1 落笔）
- 全局 `butler-v5/tests/architecture/*.test.ts`（arch guard 演进；子会话可提 PR，S1 审）
- 根 `AGENTS.md` / `CONTRIBUTING.md` / `butler-v5/AGENTS.md`

## 不擅动

- 子会话独占路径的实现细节（子会话没有主动交权，S1 不改）
- 受保护项：`wechat-inbound-butler.ts`、`.claude/**`、`pyproject.toml`

## 核心职责

1. **开局**：读 `.blackboard/state.md` 与 `butler-v5/DESIGN.md`，维护本 parallel 索引（README）与各会话卡的新鲜度。
2. **把关** 每个 `par/*` 分支合回 main 前跑全量 5-gate：
   - `bash scripts/typecheck-gate.sh`
   - `pnpm exec eslint packages/ apps/ cli/ --ext .ts --max-warnings 0`
   - `CI= pnpm test`（截绿；基线随每个 D-series 刷新进 `state.md`）
   - 改 arch guard / 文档时补 `CI= pnpm exec vitest run tests/architecture -q`
3. **合并**：`git rebase origin/main par/<area>` → 跑 gate → `git checkout main && git merge --ff-only par/<area>` → push。冲突（几乎只在共享文件）由 S1 解。
4. **记账**：每个合并推进一个 D-batch；同步 `DESIGN.md §7/§7.1` + `port-catalog.md` + `state.md`（当前主线/下一步/上一班）+ 一张 shift 卡（`shifts/YYYY-MM-DD-dXX-*.md`）。
5. **跨会话依赖**：某个会话要暴露/消费其它包新符号 → S1 登记到对应卡或直接调度，避免两会话同时改同一公共面。

## 合并协议细节

- 子会话在自身 `par/*` 完成→自测→标记 ready（发 PR 即可）。
- S1 把关通过 → ff merge 回 main → push → 更新 state.md 的 `_last_synced` / `_handoff`。

## 开工前必读

根 `AGENTS.md`（v5 必读表 7 项）+ `butler-v5/DESIGN.md` §7（Ports/并行冲突热点）+ `.blackboard/state.md`。