# D49 exec 行为审计记账（S6）交接卡（S1）

> 时间：2026-09-02 · main `22d6691f` · 前置：D48 Wave-2 前半（整理类三会话并入）

## 一句话

S6 exec 行为审计记账完成并入 main（FF，693c11bf..22d6691f）。纯 apps/api 层、纯观测/审计、不新增副作用路径。此卡同时补 D48 黑板记账（上轮 Write 故障未落盘）。

## 并入内容

| 项 | 值 |
| --- | --- |
| 分支 | `par/exec-audit`（基于 693c11bf，FF） |
| commit | `22d6691f` feat(api): exec/subprocess behavior audit accounting (D47 exec-audit, S6) — 10 files +265/−43 |
| 新文件 | `apps/api/src/exec-audit.ts`：`ExecAuditContext` + `recordExecAudit` 统一落库（经 wiring RuntimeStore 注入） |
| 覆盖执行点 | workspace-tools.ts（run_command/read_file/write_file，含 bwrap 回退）、mcp-spawn.ts→mcp-bootstrap.ts（spawned）、wechat-quality-gate.ts（close/error）、dev-quality-gate.ts（runDevVerify/listGitTouchedPaths/resolveGitBranch） |
| 事件 | `exec.executed`：detail { kind: "exec", cmd, cwd, exit, durationMs, outcome: ok/failed/spawned, … } |
| 合规 | 纯观测；不签发权限；副作用咽喉语义未变；audit await（修复 fire-and-forget 引发的 PGlite 竞态）；mcp-spawn 同步上下文用 void |

## 5-gate（S1 复核）

- lint apps：**0 警** ✅
- 全量 `CI= pnpm test`：**253 files / 1545 pass / 1 skip**（+1 file +1 test vs D48）；2 fail 均环境已知（workspace-tools.bubblewrap 缺系统沙箱、cli 符号链伪影），**无一在本批改动文件** ✅
- typecheck：**仍 1 个基线错误** `apps/api/wechat-project-surface.ts:314` exactOptionalPropertyTypes — S6 报告"tsc PASS"但未清此基线遗留（10 改动文件不含它）。**如实记录：S6 未清，属报告与真实偏差；非本批引入，不阻塞**。

## S1 待办/提示

- ⚠️ **基线 typecheck 遗留仍未清**：`wechat-project-surface.ts:314`。归 S6 已明确过但未执行。**提请 owner 决策**：S1 顺手修（3 行，属 apps 生产代码、非 S1 独家范围）/ 让 S6 补 / 留待。
- Wave-3 协调项待办：**SSOT isTerminalRunStatus**（S2 domain 导出 + barrel，S5 消费删本地；S2+S1 共同提交，勿单会话）。

## 提醒

- 共享工作树 WIP（d89385ea 弃稿）勿提交，已被 43f8a645/de3da1e2 接管。
- `par/exec-audit` 已消费，勿续开；新会话 rebase 到新 main（22d6691f）。
- D48 黑板（Wave-2 前半 sign-off + SSOT 立项）随本卡一并补入 state.md。
