---
date: 2026-08-28
produced: [shift-card]
---
# Butler v5 — R15 Archived Run-Loop Rot 闭环后班段（test-side API drift 修复）

## 项目当前态

- **HEAD**：origin/main = `74e8026f`（R14 `9f9923f7` 之上 + R15 commit：`fix(archived-test): wrap makeTestConfig in Layer.succeed(Config, ...) to resolve run-loop rot`；原 `ecd421c5` 经 amend 含 handoff 卡本身的 SHA 修正 → `74e8026f`）
- **5 gate**：
  - `pnpm typecheck` ✅（archived 不在 typecheck 覆盖范围——见"失误清单"）
  - `pnpm lint` ✅
  - `pnpm test`（production）✅ `187 files / 1096 pass / 1 skip / 0 fail`
  - `pnpm test:archived` ✅ `19 files / 83 pass / 0 fail`（R12 闭环时 81/2 — R15 修掉 2 个 run-loop rot）
  - `pnpm build` ✅（turbo no-op，no `build` script defined per package — 维持 R12 状态）
- **R12 已知债状态变化**：archived run-loop rot 2 例（`run-loop.test.ts > completes with IntentReceipt for simple message` + `fails with ContextOverflow when exceeding max iterations`）→ **R15 已修**
- **PRD 状态**：无新增 PRD；R15 是 R12 闭环时承诺"待新 scope 处理"的实测清理
- **ADR 状态**：无变更

## 新会话必读（按顺序）

1. **本卡** ← 你正在读
2. **`.blackboard/shifts/2026-08-28-r14-slack-channel-handoff.md`** —— R14 班段（最近一次大闭环）
3. **`.blackboard/shifts/2026-08-28-r11-r12-handoff.md`** —— R11+R12（含 archived rot 起源）
4. **`docs/plans/active/v5-channel-port-trigger-2026-08.md`** —— Channel Port trigger ADR（未变）
5. **`.claude/projects/-home-ailearn-projects-WFXM/memory/feedback-archived-test-rot-pattern.md`** ← **R15 新增**，根因复盘 + 排查 SOP

## R15 根因（简洁版）

`@butler/config.makeTestConfig()` 在 R12 commit `33af1722` 改为返回 plain `AppConfig` 对象（注释明示 "不再是 Effect Layer"）。archived `run-loop.test.ts` 仍按旧 API 写 `Layer.mergeAll(..., makeTestConfig())`，把 plain object 当 Layer 用。

`pnpm test:archived` 不跑 typecheck（只跑 vitest），所以类型错误 `Layer<never, any, any>` 不匹配 `AppConfig` 未被拦截。runtime 把 plain object 当 Layer 合并 → `Config` 服务在合并 Layer context 中缺失 → `runLoop` 内 `yield* _(Config)` 拿到 undefined → Effect v3 抛 `Die → RuntimeException: Not a valid effect: undefined`。

dream PASS 是因为 dream 不读 Config（仅 `MemoryService`），配置缺失不影响它。run-loop DIE 因为它在 generator header 直接 `yield* _(Config)`。

## 关键路径速查

| 用途 | 路径 |
| --- | --- |
| R15 fix 文件 | `butler-v5/_archive/packages/application/_archive/run-loop/run-loop.test.ts` |
| fix diff（conceptual） | import 加 `Config`；两处 `Layer.mergeAll(..., makeTestConfig())` → `Layer.mergeAll(..., Layer.succeed(Config, makeTestConfig()))`；test 2 `lowConfig` 同样 wrap |
| `makeTestConfig` 定义（API 现状） | `butler-v5/packages/config/src/index.ts:105` 返回 `AppConfig`，**不是 Layer** |
| `Config` Tag 定义 | `butler-v5/packages/ports/src/r2-shim.ts`（archived fixture shim，R12 加） |
| 教训 SOP | `.claude/projects/-home-ailearn-projects-WFXM/memory/feedback-archived-test-rot-pattern.md` |

## 下一步（owner 真需求出现前：**无**）

R15 是单点修复，无后续 scope。

### 候选（如 owner 给题）

按 R14 handoff 候选不变（R15 未引入新候选）：
1. Channel Port 升 first-class Core Port（多 channel 真接入后）
2. Model Port 立项（多 Provider 协议统一真出现时）
3. roadmap P5 段更新
4. 新能力 / 修 bug
5. （未来）owner 真需要启用 Slack → 另立 per-channel PRD

## 不要做

延续 R14 + R12 全部约束，新增强调：

- **不引入新 PRD / 触发 record 写** — R15 是清理不是新 scope（PRD §3.2 修订仍是 backlog）
- **不改 `@butler/config.makeTestConfig` 返回类型** — R12 的 plain AppConfig 设计是 deliberate（避免 Effect Layer 启动开销，archived 才有需要）
- **不改 `_archive` 内的 impl 文件** — `runLoop` / `dream` / `delegate-task` 等 archived 业务代码不动；R15 fix 100% 在 test 侧
- **不为 archived test 加 typecheck 覆盖** — 故意维持 `test:archived` 跑 vitest 而不跑 typecheck（archived scaffold 不是 production contract，避免 noise）；见"失误清单" #1
- **不 import `Config` 从 `@butler/ports` 到生产代码** — R14 失误清单延续：`r2-shim` 仅供 archived fixture，production 走 `@butler/persistence` 直调
- **commit 用 `--no-verify`** — pre-commit hook R8.3 已修 ROOT 但 R7.5/R11.1 protocol 保留 `git commit --no-verify`（memory: `feedback-precommit-hook-flakiness`）
- **不在 commit message body 写裸反引号 commit SHA** — R13 失误：bash 反引号当命令替换吃掉 SHA；用 single quote 包 message 或 printf + here-doc（memory: `feedback-bash-backtick-in-commit-message`）

## 失误清单（R15 新增 1 条）

1. **`test:archived` 不跑 typecheck 是设计 vs 噪音权衡，不是 bug** — 起初看到 `Layer.mergeAll(..., makeTestConfig())` 类型不匹配时想"应该让 archived 也跑 typecheck"——但 archived scaffold 是 v5 production 的反例集（`r2-shim` 14 Tag fixture + R2-era 业务代码），全跑 typecheck 会引入一连串 R2 API 退化警告噪音。**修法**：保持 `test:archived` 只跑 vitest；类型错通过 (a) 实战失败日志 + (b) 单元排查（tsx minimal repro）兜底。详见 [[feedback-archived-test-rot-pattern]] "How to apply" (a)/(b)/(c) 3 步。