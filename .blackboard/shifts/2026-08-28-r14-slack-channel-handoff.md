---
date: 2026-08-28
produced: [shift-card]
---
# Butler v5 — R14 Slack Channel Integration 闭环后班段（structural alignment scope）

## 项目当前态（生产端）

- **HEAD**：origin/main = `b6cb593d`（R13 闭环之上叠加 3 commits: `ecb224e1` docs → `555943cc` refactor + fix → `b6cb593d` test）
- **5 gate**：production `187 files / 1096 pass / 1 skip / 0 fail`（R13 基线 182/1008，+5 files / +88 net）；archived `18 files / 81 pass + 2 pre-existing run-loop rot`（同 R12 已知债，未变）
- **PRD 状态**：`docs/plans/active/v5-slack-channel-integration-2026-08.md` —— **structural alignment scope closed (2026-08-28)**；scope 已修订为"target architecture 对齐"，**不实际接入生产**
- **ADR §7 slack 行**：status `in-progress`（保留作为 Channel Port trigger 机制存在证据）+ 备注 "structural alignment done; real integration deferred indefinitely"——**不会再变 completed**（除非 owner 真需要接入时另立 per-channel PRD）
- **Channel Port 状态**：仍 `⚪ 隐性承载（conditions-admit）`（DESIGN §7.1）；R14 不升 first-class（ADR §2.1 #4）

## 新会话必读（按顺序）

1. **本卡** ← 你正在读
2. **`.blackboard/shifts/2026-08-28-r14-slack-channel-trigger.md`** —— 本班 trigger record（含 scope 决议后补段）
3. **`docs/plans/active/v5-slack-channel-integration-2026-08.md`** —— per-channel PRD（structural alignment scope closed；不实际接入）
4. **`docs/plans/active/v5-channel-port-trigger-2026-08.md`** §7 —— 触发 ADR 完成记录段（`<slack>` 行 status `in-progress` + structural-only 备注）
5. **`.blackboard/state.md`** —— 顶部 R13 班段后追 R14 班段（owner 给新会话时再写）
6. **`butler-v5/packages/adapters/src/slack/`** —— 新建的 Slack adapter 目录（mirror WeChat `packages/adapters/src/wechat/`；作为 target architecture 预留位）
7. **`.blackboard/shifts/2026-08-28-r11-r12-handoff.md`** —— R11+R12 上下文
8. **`.blackboard/shifts/2026-08-28-r13-channel-port-trigger-handoff.md`** —— R13 班段
10. **`~/.claude/projects/-home-ailearn-projects-WFXM/memory/feedback-channel-trigger-scope.md`** —— Owner 自报 channel 时先问 scope 的教训（feedback）

## 关键路径速查

| 用途 | 路径 |
| --- | --- |
| Slack adapter 目录（target architecture 预留位） | `butler-v5/packages/adapters/src/slack/` |
| Slack protocol-level（5 文件） | `butler-v5/packages/adapters/src/slack/{slack-media,slack-protocol,slack-outbound,slack-outbound-media,index}.ts` |
| Slack adapter tests（4 文件 / 81 net new） | `butler-v5/packages/adapters/src/slack/*.test.ts` |
| Slack HTTP route intake test（7 例） | `butler-v5/apps/api/src/slack-intake.test.ts` |
| Slack HTTP route（守门 `BUTLER_V5_SLACK_ENABLED`） | `butler-v5/apps/api/src/routes.ts` `POST /v1/channel/slack/events` |
| Slack 编排（apps/api 留） | `butler-v5/apps/api/src/channel-{inbound,outbound,media,outbound-media}.ts`（`handleChannelInbound` + `deliverSlackChannelReply` + `slackBotToken` + `slackOutboundEnabled` + env guards） |
| Slack env（缺省关） | `BUTLER_V5_SLACK_ENABLED=1` / `BUTLER_V5_SLACK_BOT_TOKEN=xoxb-...` / `BUTLER_V5_SLACK_SIGNING_SECRET=...`（dev phase 不启用） |
| per-channel PRD（scope closed） | `docs/plans/active/v5-slack-channel-integration-2026-08.md` |
| R14 trigger record | `.blackboard/shifts/2026-08-28-r14-slack-channel-trigger.md` |
| ADR §7 完成记录 | `docs/plans/active/v5-channel-port-trigger-2026-08.md` §7（`<slack>` 行 in-progress + structural-only 备注） |

## 下一步（owner 真需求出现前：**无**）

### 当前 scope 已闭环（structural alignment scope closed）

R14 在 structural alignment scope 下已全闭环：
- ✅ adapter 三件实装至 `packages/adapters/src/slack/`（mirror WeChat）
- ✅ adapter 层单测 81 例覆盖 PRD §3 缺项（合法/非法/重复/附件 + 文本/富媒体/失败重试 + 协议/token/网络）
- ✅ HTTP route guard 集成测试 7 例（404/401/200/400 路径）
- ✅ 5 gate 全绿（production 1096/1/0；archived 81/2 pre-existing 未变）
- ✅ commit + push origin main（`ecb224e1` + `555943cc` + `b6cb593d`）

### 已取消 / 已 deferred（不再 active）

- ❌ **R14.7 Owner 真实 Slack workspace e2e** —— cancelled（不在 scope）
- ❌ **`BUTLER_V5_SLACK_ENABLED=1` 在生产 gateway 启用** —— cancelled（不在 scope）
- ❌ **R14.8 ADR §7 改 completed 行** —— 不适用（real integration deferred indefinitely）

### 待 owner 真需要时另立 per-channel PRD 的入口

如 owner 后续真要启用 Slack 接生产（实际接 Owner 真实 workspace），按 ADR §3 trigger 机制另立 per-channel PRD：
- 克隆 `docs/plans/templates/channel-integration-prd.md` → 新 per-channel PRD
- scope 标注 "real integration"（区别本轮 structural alignment scope）
- ADR §7 `<slack>` 行 status `in-progress` → 新行 / 新 cycle（不要直接 mutate 本行；本行是 structural cycle 的 anchor）
- 走完整 ADR §4 production-ready bar 4 项：adapter 已在 + 单测已在 + 真实 workspace e2e + 5 gate

## 不要做（重申避免再撞）

- 不要碰 `.claude/settings.json` / `.cursorrules` / `AGENTS.md`（除 `[MANUAL-OVERRIDE]` operator 流程）
- 不要机械刷 state.md 顶部 `_last_synced` 日期；新班段写顶部 `_handoff:` 行后（newest-first 风格）
- 不要升 Channel Port 为 first-class（另立 ADR；R13 §2.1 决策 4）
- 不要复用 `_archive/packages/{application,infrastructure,contracts}` 入生产（`package-membership.test.ts` 第 (1) 守这条）
- 不要为生产代码 import `r2-shim` 任何内容
- 不要改 pre-commit hook；commit 用 `--no-verify`（R9.5 / R7.5 / R11.1 protocol）
- 不要为 slack 抽 channel 公共抽象（DESIGN §7.1 + §18 "不预先为架构完整造抽象"；WeChat + Slack 已落地但抽象仍 YAGNI —— 待第三个 channel 真需求再说）
- 不要把 Slack adapter 的协议级代码搬回 apps/api/src/（555943cc 已镜像 WeChat 结构）
- **不要在 owner 没明示启用前设 `BUTLER_V5_SLACK_ENABLED=1` 或跑 owner 真实 workspace e2e** —— 当前 scope 是 structural alignment only（dev phase 目标 = target architecture 对齐；WeChat 是唯一在生产 channel）

## 我的失误（避免重蹈）

- **Owner "X 接生产" 不一定 = real integration；可能 = structural alignment** —— R14.1 接 owner dialog "Owner 自报 Slack" 误读为 "实际接入生产意图"，照搬 per-channel PRD 模板（含 Owner 真实 workspace e2e + 完整 production-ready bar 5 项）+ ADR §7 trigger 行 status `in-progress` 暗示进行中。本质 scope 漂移。**修法**：Owner 自报任何 channel / integration 时，**先问 scope**（real integration vs structural alignment vs experimental）；per-channel PRD §1 必须显式标注 scope；ADR §3 trigger 机制未来可考虑增"scope 维度"。详见 [[feedback-channel-trigger-scope]]。

- **`@butler/adapters/<subpath>` import 必须带 `/index.js` 后缀** —— 初次 import `@butler/adapters/slack` 报 TS2307 "Cannot find module"。**根因**：exports map 只有 `./slack/index.js` → `./src/slack/index.ts`（与 `./postgres/index.js` 同款），bare `@butler/adapters/slack` 不 match 任何 export key。**修法**：所有 caller 一律用 `@butler/adapters/slack/index.js`（已在 555943cc 落地）；以后新加 `@butler/adapters/<x>` 必须配套 `./x/index.js` export + import 用 full path。

- **`git add <dir>` 会包含全部内容（含新 test 文件）** —— refactor commit 555943cc 本意只搬 src 代码，结果 4 个 test 文件一同进去。**根因**：`git add butler-v5/packages/adapters/src/slack/` 是目录级 add，递归包含 `*.test.ts`。**修法**：以后 `git add <specific-file>` 指定文件名；如要批量 add 用 `git add <dir>/*.ts -- ':!*.test.ts'` 排除 test。

- **`describeSlackFiles` whitespace-only name 漏 fallback** —— 原代码 `typeof === "string" ? trim() : "attachment"` 在 `"   "` 上 trim 后 `""` 不进 else 分支，返回 `""`。adapter 测试 "treats empty file name as attachment" pin down 后修法 `(... .trim() : "") || "attachment"`。**根因**：原 isinstance check 在 trim 后失效；测试覆盖前的盲区。**修法**：parser 类函数写测试时**必须**覆盖 empty/whitespace boundary；本 PR 555943cc 已修。

## 时序与依赖

- R11 + R12 closure（9 commits, `8084fcc8` ... `7949096e`）
- R13 Channel Port Trigger ADR（3 commits, `a740cae0` ... `5aac4046`）
- R14 Slack Channel Integration（3 commits, `ecb224e1` ... `b6cb593d`）—— 含 R14.1 + R14.5 + R14.6；**scope = structural alignment only**（owner dialog 后补）
- R14 scope 修订（1 commit, `docs(slack): scope revised to structural alignment only`）—— PRD + ADR §7 + trigger/handoff 卡 + memory + feedback 同步
- 5-gate 复核：CI= pnpm typecheck && CI= pnpm lint && CI= pnpm test && CI= pnpm test:archived
  - production: 1096 / 1 / 0 ✅
  - archived: 81 + 2 pre-existing ⚠️（同 R12 baseline）

## Commit 链阅读路径（按发现顺序）

```
docs(slack): scope revised to structural alignment only   ← (本卡待 commit)
b6cb593d  test              slack-intake HTTP route guards
555943cc  refactor          Slack code move + describeSlackFiles fix
ecb224e1  docs              R14 PRD + ADR §7 trigger + shift card
5aac4046  docs(blackboard)  R13 shift handoff card for next session
2e420d8e  docs(blackboard)  R13 班段 — channel-port-trigger ADR 收口记录
```

## 立刻能上手的最小动作

```bash
cd /home/ailearn/projects/WFXM
git pull                                                    # HEAD = b6cb593d
git log --oneline -6                                        # 看 R14 链
CI= pnpm typecheck && CI= pnpm lint && CI= pnpm test && CI= pnpm test:archived  # 期望 1096/1/0
head -5 .blackboard/shifts/2026-08-28-r14-slack-channel-handoff.md  # 本卡
ls butler-v5/packages/adapters/src/slack/                   # 5 文件（mirror WeChat；target architecture 预留位）
```

如果 user 给题（且明确 owner 真需要启用 Slack 接生产），按本卡 §"待 owner 真需要时另立 per-channel PRD 的入口" 走。
如果 user 没指题，等 owner —— 别自动启动 R14.7。