# Butler v5 AI Guard 迁移清单（人工执行）

> **状态**：Proposed / manual-only  
> **排期**：Owner 有空时执行；**不阻塞** v5 功能交付与日常 push。  
> **原因**：根 `.cursorrules`、`.claude/settings.json`、`scripts/ai_guard/*.py` 和 `butler-v5/AGENTS.md` 均属于保护面；普通 Agent 不应在同一次任务中修改守卫并解除自身约束。  
> **关联**：[`v5-product-boundaries-2026-08.md`](../decisions/v5-product-boundaries-2026-08.md) · [`v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md)

## 需要纠正的旧前提

- 根规则仍把 `butler/core`、v4 九层与 v4 Python gates 当唯一主线；
- `butler-v5/AGENTS.md` 把未接线的 Effect Application/Infrastructure 描述为完整生产架构；
- `butler-v5/AGENTS.md` 的“所有可恢复错误必须走 Effect ADT”“模块级 Map 一律可疑”等规则与当前生产 async/await delivery shell 不完全一致；
- 根 PostToolUse/Stop 流程主要覆盖 v4 文件和 v4 黑板习惯；
- v5 的真实承重文件、唯一 schema、生产 Loop 与权限入口没有同等级保护。

## 人工迁移步骤

1. 在 GitHub 创建 guard migration issue，链接产品边界与生产架构 SSOT。
2. 备份当前规则与 hook 输出，确认已有 v4 保护仍需保留到何时。
3. 在 `butler-v5/AGENTS.md` 区分：
   - 生产路径约束；
   - 未接线脚手架约束；
   - 目标 Policy/ScopedGrant/Sandbox 约束。
4. 把以下 v5 文件加入承重保护候选：
   - `apps/api/src/wechat-inbound-butler.ts`
   - `packages/runtime/src/agent-kernel.ts`
   - `packages/runtime/src/bridge.ts`
   - `packages/persistence/src/migrations/0001_initial.sql`
   - `apps/api/src/workspace-tools.ts`
   - `apps/api/src/capability-guard.ts`
5. 新增或调整 hook，使修改 v5 TypeScript 时运行对应测试、typecheck、lint 与 architecture tests。
6. 保留禁止 secret、wildcard import、危险 shell、绕过测试和自改守卫的规则。
7. 不删除 v4 保护，直到确认 v4 只读归档且无运营依赖。
8. 由人工修改保护文件，并按仓库要求使用 `[MANUAL-OVERRIDE]`。

## 验收

- Agent 新会话首先读 v5 SSOT，不再从 v4 文档推断；
- 修改生产 Loop、schema、工具沙箱或权限入口会触发 v5 专项验证；
- 守卫本身仍不能被普通 Agent 修改；
- 规则不强迫生产代码伪装成未接线 Effect 架构；
- v4 历史保护移除有独立、可审计的人工作业。
