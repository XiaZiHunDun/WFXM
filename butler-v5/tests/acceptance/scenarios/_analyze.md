# Acceptance Realistic Scenarios — 产品层行为分析

生成时间：2026-09-04（35 场景自动跑出）

## 总览

- 场景数：35
- 通过：35 / 失败：0
- 触发 approval：9 次
- 工具调用总数：28
- reply 字符总数：4903

## 按类别汇总

### A-concrete（10 场景，10 通过）

| ID | 标题 | 工具 | 审批 | 状态 |
|---|---|---|---|---|
| A1 | 读 README | 1 | 0 | ✅ |
| A2 | 改 user 路由支持手机号登录 | 2 | 1 | ✅ |
| A3 | 跑 pnpm test | 1 | 0 | ✅ |
| A4 | 昨天我们改了什么 | 0 | 0 | ✅ |
| A5 | 删 dead import | 2 | 1 | ✅ |
| A6 | timeout 可配 | 2 | 1 | ✅ |
| A7 | git log -5 | 1 | 0 | ✅ |
| A8 | 生成 PR 描述 | 1 | 0 | ✅ |
| A9 | 跑 typecheck | 1 | 0 | ✅ |
| A10 | 加 unit test | 1 | 0 | ✅ |

### B-open（10 场景，10 通过）

| ID | 标题 | 工具 | 审批 | 状态 |
|---|---|---|---|---|
| B1 | v5 现在有什么问题 | 0 | 0 | ✅ |
| B2 | 下一步该做什么 | 0 | 0 | ✅ |
| B3 | 新接手导览 | 0 | 0 | ✅ |
| B4 | 最近 3 天做了什么 | 0 | 0 | ✅ |
| B5 | 架构 risk | 0 | 0 | ✅ |
| B6 | 我撞过哪些坑 | 0 | 0 | ✅ |
| B7 | 设计哲学 | 0 | 0 | ✅ |
| B8 | 我没用过的功能 | 0 | 0 | ✅ |
| B9 | owner 应该关心什么 | 0 | 0 | ✅ |
| B10 | 1 周 focus | 0 | 0 | ✅ |

### C-edge（10 场景，10 通过）

| ID | 标题 | 工具 | 审批 | 状态 |
|---|---|---|---|---|
| C1 | y 当确认 | 0 | 0 | ✅ |
| C2 | 好的 当确认 | 0 | 0 | ✅ |
| C3 | 👌 当确认 | 0 | 0 | ✅ |
| C4 | 长消息 spam | 0 | 0 | ✅ |
| C5 | 模糊 优化 | 0 | 0 | ✅ |
| C6 | 跨天 上次聊到哪 | 0 | 0 | ✅ |
| C7 | 两个 task 一起 | 1 | 0 | ✅ |
| C8 | 重复确认 | 2 | 1 | ✅ |
| C9 | 撤销刚才 | 0 | 0 | ✅ |
| C10 | 多语言混合 | 1 | 0 | ✅ |

### D-combo（5 场景，5 通过）

| ID | 标题 | 工具 | 审批 | 状态 |
|---|---|---|---|---|
| D1 | 写 + 跑 test + 失败 + 修 + 再跑 | 3 | 2 | ✅ |
| D2 | 看看 后续追问 | 2 | 0 | ✅ |
| D3 | 先 read 现在改 | 2 | 1 | ✅ |
| D4 | 被打断 resume | 2 | 0 | ✅ |
| D5 | 写完 问安全吗 | 3 | 2 | ✅ |

## 每场景 reply 抓取（用于人工 review）

### A1 — 读 README（A-concrete）

**turn 1**

> in: 帮我读 /ws/README.md

< 已读 README.md：项目是 butler-v5 — 函数式架构微信编码管家。主要功能：编码、会话记忆、微信入站。

想深入看哪部分？

_decision=Respond | toolCalls=1 | replyLen=69_

### A2 — 改 user 路由支持手机号登录（A-concrete）

**turn 1**

> in: 帮我改 user 路由支持手机号登录

< [待审批] Confirm write_file on apps/api/src/routes/user.ts?
审批编号: 2f11bcd1-61d0-4756-8c8a-285bed98e4ca
回复「确认」批准，或「拒绝」取消。

_decision=WaitForApproval | toolCalls=2 | replyLen=117_

### A3 — 跑 pnpm test（A-concrete）

**turn 1**

> in: 跑 pnpm test 看有没有 fail

< 已跑完。266 files / 1712 passed / 1 skipped，0 fail。

_decision=Respond | toolCalls=1 | replyLen=47_

### A4 — 昨天我们改了什么（A-concrete）

**turn 1**

> in: 昨天我们改了什么

< 昨天（2026-09-03）我们 7 个 commit：
1. test(acceptance) wechat end-to-end harness
2. docs(plans) fix broken doc links
3. chore gitignore .trae
4. docs(superpowers) fill 2026-09-XX
5. ci(butler-v5) explicit acceptance step
6. chore(ai-guard) pre-commit hook sync
7. chore(blackboard) record session close

_decision=Respond | toolCalls=0 | replyLen=296_

### A5 — 删 dead import（A-concrete）

**turn 1**

> in: 把 packages/domain/src/foo.ts 里没人用的 import 删掉

< [待审批] Confirm write_file on packages/domain/src/foo.ts?
审批编号: eab79a87-2563-4345-a344-e0eb4aaadf26
回复「确认」批准，或「拒绝」取消。

_decision=WaitForApproval | toolCalls=2 | replyLen=116_

### A6 — timeout 可配（A-concrete）

**turn 1**

> in: 把 utils.ts 的 timeout 改成可配的

< [待审批] Confirm write_file on apps/api/src/utils.ts?
审批编号: 2496b3f0-b593-4d8c-98dd-444d14b36ed9
回复「确认」批准，或「拒绝」取消。

_decision=WaitForApproval | toolCalls=2 | replyLen=111_

### A7 — git log -5（A-concrete）

**turn 1**

> in: git log -5 给我看

< 最近 5 个 commit：
09e0cdfb chore(blackboard)
c4a0bcb8 chore(ai-guard)
013d1095 ci(butler-v5)
f3716d5f docs(superpowers)
0f1ef949 chore

_decision=Respond | toolCalls=1 | replyLen=131_

### A8 — 生成 PR 描述（A-concrete）

**turn 1**

> in: 帮我写个 PR 描述，把最近 7 个 commit 整理出来

< PR 描述草稿：
## 摘要
- 新增微信端到端模拟验收 harness（4 acceptance 文件 / 11 用例）
- 修复 doc 链接 + 清理 spec placeholder
- CI 纳入 acceptance + pre-commit hook 同步闭环

## 测试
- 全量回归 266/1712/1skip pass
- typecheck/lint 0 警

_decision=Respond | toolCalls=1 | replyLen=192_

### A9 — 跑 typecheck（A-concrete）

**turn 1**

> in: 跑下 typecheck

< typecheck 7 packages 全绿。

_decision=Respond | toolCalls=1 | replyLen=24_

### A10 — 加 unit test（A-concrete）

**turn 1**

> in: 给 packages/runtime/src/run-engine.ts 加个 unit test 覆盖 conflict 路径

< 看了 run-engine.test.ts，已经有 ActiveMainRunConflict 测试（line 271 + 448）。如要补充，建议加：
- 并发 2 个 inbound 到同 convId 验证第二个抛
- resumeRun 错误状态（已 terminal）抛错

要加哪个？

_decision=Respond | toolCalls=1 | replyLen=148_

### B1 — v5 现在有什么问题（B-open）

**turn 1**

> in: v5 现在有什么问题？

< 按我目前观察，v5 production-ready 但有几类未消化项：
- §18 20 项延后触发（等真实场景撞）
- 真实 LLM 输出质量未量化（scripted harness 只能验 wiring）
- WeChat 端 UX 未 owner 实测过（移动端格式 / 长消息）
- 没有使用率埋点（哪些命令真在用未知）

要展开哪条？

_decision=Respond | toolCalls=0 | replyLen=173_

### B2 — 下一步该做什么（B-open）

**turn 1**

> in: 下一步该做什么？

< 按你刚扫完代码卫生 + 验收基建 + hook sync 闭环的状态，建议：
1. 跑 realistic scenarios 找真痛点（这批）
2. 看 owner 实测 1 周后输出 owner 视角笔记
3. 加延迟 + 失败可观测埋点

短期 ROI 排第 1。

_decision=Respond | toolCalls=0 | replyLen=135_

### B3 — 新接手导览（B-open）

**turn 1**

> in: 我刚接手这个项目，给我导览一下

< v5 = 函数式架构微信编码管家（Effect-TS）。
核心概念：
- 6 个 Port + 7 个核心（runtime/persistence/llm）
- Acceptance 走 runButlerLoop（INTAKE_ENABLED=0）
- 副作用咽喉 = policy-gate + capability-boundary
- 3 层记忆 = Transcript / Durable Memory / Project Knowledge

入口：
- DEV：`pnpm dev`
- TEST：`pnpm vitest run tests/acceptance --pool=forks`
- 微信：POST /v1/wechat/inbound

想深入哪块？

_decision=Respond | toolCalls=0 | replyLen=341_

### B4 — 最近 3 天做了什么（B-open）

**turn 1**

> in: 最近 3 天你帮我做了什么

< 本会话 7 commit：
1. 微信端到端模拟验收 harness（4 文件 / 11 用例）
2. doc 链接修复 + .trae/ gitignore
3. specs/ placeholder 日期清理
4. CI 纳入 acceptance
5. pre-commit hook 同步闭环
6. blackboard 同步

外加 D-series 35 batch 之前的工作。
需要我列具体 commit 吗？

_decision=Respond | toolCalls=0 | replyLen=213_

### B5 — 架构 risk（B-open）

**turn 1**

> in: 架构上有什么 risk

< 按 DESIGN §13 + §20 现状：
- 高 risk：Core 不反向依赖 adapters（已锁）；Effect TS 边界（6 LLM callsite timeout 已加）
- 中 risk：MCP token-passthrough 走 manifest oauthAudience fail-closed；approval runtime hardening 已闭环
- 低 risk：文档 hygiene（最近扫过）

真实 risk：
- LLM 真实输出质量未量化（scripted fixture 测不出）
- 20 §18 延后项未撞（不是 bug，是产品 gap）

_decision=Respond | toolCalls=0 | replyLen=299_

### B6 — 我撞过哪些坑（B-open）

**turn 1**

> in: 我撞过哪些坑？

< 近期已知 issue：
- ① healthzUp 集成测试 skipIf 在异步 beforeAll 求值 → 4 双向网络守卫从未真跑（已修）
- ② runButlerLoop 异常丢消息（已修：catch 降级 reply）
- ③ pre-commit hook 源/安装副本漂移（已闭环 install+postinstall+CI drift）
- ④ D42 follow-up placeholder 日期（已清）
- ⑤ acceptance 用例 default conversationId 稳定撞 ActiveMainRunConflict（已每用例独立）

_decision=Respond | toolCalls=0 | replyLen=291_

### B7 — 设计哲学（B-open）

**turn 1**

> in: 项目的设计哲学是什么？

< v5 核心原则：
- Effect-TS 严格边界：纯函数 + 端口注入
- 显式承认 vs 修复：D-series 30+ 承认项（arch guard 防再犯）
- 触发条件式设计：§18 trigger 制度，20 延后项等真撞
- 文档先行：DESIGN.md 21 段 + audit guard 锁
- 不造第二实现：Memory/Channel Port 走 trigger-conditioned，不硬物化

_decision=Respond | toolCalls=0 | replyLen=211_

### B8 — 我没用过的功能（B-open）

**turn 1**

> in: 哪些功能是我没用过的

< （诚实回答）我没有使用率埋点，所以无法直接告诉你哪些真没用。但按设计意图，以下能力可能还没在你身上落地：
- /记住 + durable memory candidate（除非你显式确认才转 confirmed）
- project knowledge recall（除非你喂资料）
- 跨 project recall（G5 工具，需要多 project）

如想知道「哪些我已实现但实测没人用」，需要加埋点。

_decision=Respond | toolCalls=0 | replyLen=206_

### B9 — owner 应该关心什么（B-open）

**turn 1**

> in: 作为 owner 我应该关心什么

< 你该关心的（按频率/影响）：
- 每天：bot reply 是否真帮上忙（最直接）
- 每周：哪些命令在用、哪些 dead；哪类请求 bot 答得不对
- 每月：架构 §18 20 项是否撞到；MCP / approval / memory 是否有边界 case
- 季度：v5 vs 其他工具的 UX gap；新需求能否低门槛实现

_decision=Respond | toolCalls=0 | replyLen=166_

### B10 — 1 周 focus（B-open）

**turn 1**

> in: 接下来 1 周我该 focus 什么

< 建议本周 focus 顺序：
1. 跑完 realistic scenarios 35 个，写分析
2. 选 1-2 个最痛的格式 / 延迟 / approval 边界问题修
3. 加 LLM 真实质量记录（fixture-recording）
4. owner 视角实测 1 周（你手动）
5. 视情况重启某条延后项

_decision=Respond | toolCalls=0 | replyLen=159_

### C1 — y 当确认（C-edge）

**turn 1**

> in: y

< 当前对话没有待审批的操作。

_decision=Respond | toolCalls=0 | replyLen=13_

### C2 — 好的 当确认（C-edge）

**turn 1**

> in: 好的

< 当前对话没有待审批的操作。

_decision=Respond | toolCalls=0 | replyLen=13_

### C3 — 👌 当确认（C-edge）

**turn 1**

> in: 👌

< 当前对话没有待审批的操作。

_decision=Respond | toolCalls=0 | replyLen=13_

### C4 — 长消息 spam（C-edge）

**turn 1**

> in: 请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请帮我请...

< 检测到字符「请」重复 200 次。请发具体需求。

_decision=Respond | toolCalls=0 | replyLen=24_

### C5 — 模糊 优化（C-edge）

**turn 1**

> in: 优化一下

< 优化什么？范围很大。常见的方向：
- 代码质量（lint / typecheck / deadcode）
- 性能（profile + 找热点）
- UX（reply 格式 / 延迟）
- 架构（§18 延后项 / 端口物化）

请告诉我要优化哪条。

_decision=Respond | toolCalls=0 | replyLen=125_

### C6 — 跨天 上次聊到哪（C-edge）

**turn 1**

> in: 上次我们聊到哪

< （按当前会话）最近我们：
- 完成了 acceptance harness 收口
- doc 卫生 + hook sync 闭环
- state.md + MEMORY.md 同步

如查历史会话：需用 recall_history 工具（受 working set 窗口限制）。

_decision=Respond | toolCalls=0 | replyLen=140_

### C7 — 两个 task 一起（C-edge）

**turn 1**

> in: 帮我看 foo.ts 顺便把 bar.ts 也改了

< 先看 foo.ts。bar.ts 你想改什么？

_decision=Respond | toolCalls=1 | replyLen=23_

### C8 — 重复确认（C-edge）

**turn 1**

> in: 帮我写个东西

< [待审批] Confirm write_file on foo.txt?
审批编号: d24185b3-08d0-45de-a535-e33263ef7320
回复「确认」批准，或「拒绝」取消。

_decision=WaitForApproval | toolCalls=1 | replyLen=97_

**turn 2**

> in: 确认

< ✅ 文件已写入
wrote foo.txt (1 chars)

_decision=Respond | toolCalls=1 | replyLen=31_

**turn 3**

> in: 确认

< 当前对话没有待审批的操作。

_decision=Respond | toolCalls=0 | replyLen=13_

### C9 — 撤销刚才（C-edge）

**turn 1**

> in: 撤销刚才

< 撤销哪个操作？请说具体文件名。

_decision=Respond | toolCalls=0 | replyLen=15_

### C10 — 多语言混合（C-edge）

**turn 1**

> in: Read the 🐛 README 📖 pls，给我摘要 in English

< Quick summary: v5 is a WeChat-based coding assistant (Effect-TS, functional arch).

_decision=Respond | toolCalls=1 | replyLen=82_

### D1 — 写 + 跑 test + 失败 + 修 + 再跑（D-combo）

**turn 1**

> in: 加个 helper 跑下测试

< [待审批] Confirm write_file on packages/runtime/src/helper.ts?
审批编号: a1abde5d-80e1-4b8e-b8be-83d904fefe77
回复「确认」批准，或「拒绝」取消。

_decision=WaitForApproval | toolCalls=1 | replyLen=120_

**turn 2**

> in: 确认

< ✅ 文件已写入
wrote packages/runtime/src/helper.ts (42 chars)

_decision=Respond | toolCalls=1 | replyLen=55_

**turn 3**

> in: 跑 test

< [待审批] Confirm write_file on packages/runtime/src/helper.ts?
审批编号: baf67f0a-d9c4-4e4c-bdbd-3beee06893d1
回复「确认」批准，或「拒绝」取消。

_decision=WaitForApproval | toolCalls=1 | replyLen=120_

### D2 — 看看 后续追问（D-combo）

**turn 1**

> in: 看看 apps/api/src/owner-routes.ts

< 已读 owner-routes.ts（1200+ 行，分 7 子模块）。要细看哪个？

_decision=Respond | toolCalls=1 | replyLen=42_

**turn 2**

> in: owner-routes/memories.ts

< 已读 owner-routes.ts（1200+ 行，分 7 子模块）。要细看哪个？

_decision=Respond | toolCalls=1 | replyLen=42_

### D3 — 先 read 现在改（D-combo）

**turn 1**

> in: 把 user.ts 的 password validator 换成 zod schema

< [待审批] Confirm write_file on apps/api/src/user.ts?
审批编号: fbaab8c3-93fc-461f-85e8-dd7f11a61a93
回复「确认」批准，或「拒绝」取消。

_decision=WaitForApproval | toolCalls=2 | replyLen=110_

### D4 — 被打断 resume（D-combo）

**turn 1**

> in: 开始重构 butler-v5/packages/runtime

< 已读 index.ts。建议先列重构 plan 给你确认。

_decision=Respond | toolCalls=1 | replyLen=29_

**turn 2**

> in: 列出 plan 给我看

< 已读 index.ts。建议先列重构 plan 给你确认。

_decision=Respond | toolCalls=1 | replyLen=29_

### D5 — 写完 问安全吗（D-combo）

**turn 1**

> in: 加个 /debug 命令

< [待审批] Confirm write_file on apps/api/src/wechat-inbound-commands.ts?
审批编号: 1a7d8210-45e9-48b4-b5bb-3c670ee4b773
回复「确认」批准，或「拒绝」取消。

_decision=WaitForApproval | toolCalls=1 | replyLen=129_

**turn 2**

> in: 确认

< ✅ 文件已写入
wrote apps/api/src/wechat-inbound-commands.ts (25 chars)

_decision=Respond | toolCalls=1 | replyLen=64_

**turn 3**

> in: 它安全吗

< [待审批] Confirm write_file on apps/api/src/wechat-inbound-commands.ts?
审批编号: c3c75960-56ac-4643-8c89-7209a48e3643
回复「确认」批准，或「拒绝」取消。

_decision=WaitForApproval | toolCalls=1 | replyLen=129_
