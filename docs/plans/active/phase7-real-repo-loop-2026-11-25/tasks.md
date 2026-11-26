# Phase 7（v2）— WFXM Web 对话驱动真实仓库开发（Tasks）

> 对应 [spec.md](spec.md)。不自动 commit / push。
> 原则：LingWen 代码一律由 WFXM 经 Web 对话产出；本执行方只做启动、只读核查、构建与浏览器验证。

## T1 WFXM P0 修复
- [x] F1 `conversation-loop.ts`：未知工具错误附带可用工具名；决策标签被当工具时给出正确指引
- [x] F2 `subagent-worker.ts`：抽出 `buildChildSystemPrompt`，明确「用工具落地 / 完成前核对 / 才允许纯文本收尾」
- [x] F3 `subagent-worker.ts`：`MAX_CHILD_ITERATIONS` 12→20；`maxIterations` 与 `maxToolCalls` 一致传入
- [x] F4 `subagent-worker.ts`：失败回复带错误码 + 最后 trace，不再只回「调用失败」
- [x] F5 outbox payload 的 task 改为全文（根因：`TASK_PREVIEW_CHARS=200`），新增回归测试
- [x] F6 `wechat-inbound-butler.ts`：新增 `BUTLER_V5_MAX_LOOP_ITERATIONS` 覆盖（默认仍 5）
- [x] F2b `conversation-loop.ts`：`toolFirst` 模式下纯文本提前收尾最多 2 次提示继续，新增单测

## T2 修复验证
- [x] `conversation-loop.test.ts` 增加未知工具提示断言
- [x] 新增 `buildChildSystemPrompt` 单测
- [x] 跑 `pnpm exec vitest run`（上述 + `wechat-dev-delegate.test.ts`）→ 30 passed
- [x] 跑根脚本 `typecheck` / `lint`（typecheck 通过）

## T3 重启 Web 入口
- [x] `BUTLER_V5_DEMO_REAL_LM=1`…（实际：`BUTLER_V5_DEMO_REAL_LLM=1` + 4522 + workspace + 18 轮）
- [x] 验证 `POST /demo/api/chat` 可用；子代理首轮只读不收工的问题经 F2/F2b 复现并修复

## T4 LingWen M1 骨架
- [x] 对话要求 WFXM 补齐 `src/app` 最小页面与 scripts（子代理写 3 个文件）
- [x] 只读核查工作区；`pnpm build` 通过（4 个静态页）

## T5 LingWen M2 数据层
- [x] 对话统一表结构：`src/lib/db.js` 五表 + WAL + 外键，导出 initDb/getDb/closeDb
- [x] `tests/db.test.mjs` 重写：8 tests passed；`pnpm test` + `typecheck` 通过
- [x] 新增 `src/lib/repo.js`：14 个导出（books/bible/outlines/chapters/llm_logs 访问）

## T6 LingWen M3 API
- [x] books / bible / outline / chapters / generate(流式) / check / export 路由
- [x] 核查路由文件与类型（10 个路由，`pnpm build` 通过；next.config 由 WFXM 自行补 serverExternalPackages 与 extensionAlias）

## T7 LingWen M4 UI
- [x] `/` 书架页（列表/新建/删除/进入工作台）
- [x] `/books/[id]` 三栏工作台（大纲+章节 / 编辑器+AI 流式续写 / 设定集+体检+导出）
- [x] 备注：M4-2 需求 2498 字符被 Demo Console 2000 上限拒绝，拆成 M4-2a/2b 两轮完成

## T8 收口
- [x] `pnpm build` 通过（含 `/books/[id]` 与 10 个 API 路由）
- [x] 启动 `next start -p 3210` 并用 Playwright 验证书架 + 工作台（3 栏、正文载入、体检）
- [x] 真实 LLM 烟测：建书→设定→大纲→建章→流式生成→落库→检查→导出
- [x] 回填 spec §6（轮数、失败、根因、缺陷分级、证据）
- [x] 未执行 commit/push（等待 owner 指令）

## T9 第二轮闭环缺陷修复（F7–F13）
- [x] F7 未知工具近似名提示（list_files → list_dir）
- [x] F8 spam 长度上限可配置并与 Demo 8000 对齐
- [x] F9 失败信封提示后台子任务
- [x] F10 子代理 worker `onEvent` + `GET /demo/api/status`
- [x] F11 `delegationClaimGuard`：声称已派但未调用工具时纠正一次
- [x] F12 子代理 stuck-loop 阈值 6 + prompt 约束重复命令
- [x] F13 `read_file` 支持 offset/limit，24KiB 截断提示
- [x] 新增/更新单测 5 个文件 62 passed；typecheck 通过；4522 重启验证

## T10 LingWen 产品完善（第二轮对话）
- [x] A：书籍设置、章节删除/排序、大纲编辑、按大纲建章、全局统计
- [x] B：按大纲续写、AI 检查、可中止生成、生成/检查互斥
- [x] C：自动保存、Cmd/Ctrl+S、beforeunload、书架统计条
- [x] D：作品内流式 AI 助手
- [x] 回归修复：补回被覆盖的设置面板与章节 ↑↓
- [x] build + Playwright + 真实 LLM 复测；未 commit/push

## T11 第三轮：版本历史 + edit_file（F14）
- [x] F14 `edit_file`：workspace-tools 唯一片段替换 + 单测 3 条；接入 ALLOWED_CAPABILITIES / 子代理默认能力 / pregrant / alwaysConfirm / 提示词 / 审批文案
- [x] 受影响单测更新（tools 14 descriptors、delegate-capabilities、policy-gate、workspace-tools）→ 93 passed；typecheck 通过
- [x] 重启 4522（新工具生效）
- [x] E1 后端：`chapter_revisions` 表 + repo 五个函数 + 3 路由 + 三处自动快照；API 烟测通过（manual/pre-restore/restore/404）
- [x] E2 UI：「历史版本」按钮 + 面板 + 只读预览 + 二次确认恢复；Playwright 实测 4 条版本、恢复生效、旧功能按钮仍在
- [x] 记录遗留：审批恢复后续跑预算不足（P2），需再发一轮继续；未 commit/push

## T12 审批恢复续跑预算（F15）
- [x] `approval-resume.ts`：写类审批（write_file/edit_file）恢复后保留 exec 工具续跑；仅 `run_command` 成功走快速 ack
- [x] 续跑轮次从 `BUTLER_V5_MAX_LOOP_ITERATIONS` 读取（默认仍 5），不再硬编码
- [x] 系统提示区分「写类续跑」与「命令后只读」两种模式
- [x] `edit_file` 纳入 `EXEC_TOOL_NAMES` / dev session 授权 / intake 判定 / dev 质量校验 / 意图正则
- [x] 单测 3 条 + intake 断言；相关测试 93 + 91 passed，typecheck 通过
- [x] 提交 F14 与版本历史（LingWen `0d287e13`）；F15 待提交

## T13 run_command 超时（F16）
- [x] `workspace-tools.ts` 新增 argv 感知默认超时（长任务 120s / 普通 5s）+ 显式 env 覆盖优先
- [x] `tool-boundary.ts` 的 `toolTimeoutMs` 接收 args；`capability-boundary` 在调用时按 args 计算超时
- [x] 单测：pnpm build/node --test → 120s；ls/无 argv → 5s；slirp/env 覆盖保持通过
- [x] typecheck 通过；相关 77 测试通过

## T14 失败信封误导与审批 resource（F17）
- [x] `formatFailureEnvelope` 增加 `delegated`/`toolCalls`：已委派不再提示重发，已执行工具提示部分生效
- [x] `withLlmFailureEnvelope` 检测 `delegate_to_subagent` / `StartChildRun` trace 并传入上下文
- [x] `resourceForTool` 支持 `edit_file`（审批问题显示文件路径，不再显示会话 id）
- [x] 单测 4 条（2 信封分支 + resource + 既有），57 测试通过；typecheck 通过；待提交

## T15 第三轮闭环缺陷（F18–F19）
- [x] F18 `spawnCaptured`：POSIX `detached: true` + abort 时 `kill(-pid)` 整组回收，杜绝 `pnpm build` 超时后的孤儿构建
- [x] F18 单测：派生 30s 孙进程 → 1.5s 超时 → 孙进程已退出（workspace-tools 11 passed）
- [x] F19 工具额度用尽后跳过 tool-first / delegation-claim 提示，避免自相矛盾与整单重派
- [x] F19 单测：`maxToolCalls=1` 后纯文本总结被接受（conversation-loop 29 passed）
- [x] 全仓 typecheck 通过；4522 已重启加载新代码

## T16 LingWen 批次 F（JSON 备份/恢复 + 全局搜索，经 Web 对话）
- [x] F1 后端：`GET /api/books/[id]/export/json` + `POST /api/books/import/json`（校验/事务/id 映射/重名后缀）
- [x] F1 验证：导出 3123 B、404/400 分支、导入 201 且章节/字数/大纲/设定数量一致
- [x] F2 后端：`GET /api/search`（三表 LIKE+ESCAPE、JOIN books、snippet、limit≤50、真实 total）
- [x] F2 UI：书架 300ms 防抖搜索浮层（Esc/点外关闭/无结果）+ 章节结果跳 `?chapter=` + 工作台自动选中
- [x] Playwright：10 条结果、跳转后正文 423 字、章节高亮、既有功能按钮仍在
- [x] typecheck/build 通过（24 条路由）；未提交（等待 owner 指令）

## T17 LingWen 批次 G（备份入口 / 润色 / 写作日历，经 Web 对话）
- [x] G1 书架「导入 JSON」+ 书卡/设置面板「导出 JSON」+ 搜索键盘导航（↑↓/Enter/Esc/悬停）
- [x] G1 验证：导入提示与列表刷新、键盘跳转 `?chapter=`、详情页导出链接
- [x] G2 `POST /api/chapters/[id]/polish` 流式 + 工作台预览/应用/撤销/取消
- [x] G2 验证：真实 LLM 流式、应用 423→399、撤销回 423、既有按钮仍在
- [x] G3 `writing_sessions` / `app_settings` 迁移 + repo 四函数 + PATCH 增量 + 两个 API + 书架今日进度与 14 天柱图
- [x] G3 验证：旧库平滑迁移、daily/goal API、UI 柱图与目标设置
- [x] G4 口径修复：restore 记账、删除记负、展示 clamp 0..100；新增 `tests/writing-stats.test.mjs`
- [x] G4 验证：pnpm test 11 passed、受控 PATCH/restore 差异入库、书架显示 0 而非 -28%
- [x] typecheck/build 通过；未提交（等待 owner 指令）

## T18 子代理 LLM 失败自动重试（F20）
- [x] `isRetryableLlmFailure`：`llm failure` 且无 `write_file`/`edit_file` trace 才允许重试
- [x] worker 在首次失败后自动重跑一次子任务，避免 owner 手动重发与重复执行
- [x] 单测：首次 complete 失败、第二次成功 → 重试后回复送达（subagent-worker 19 passed）
- [x] 修正 2 条既有测试「最后一条消息即 tool 结果」的假设（预算提示会追加 system 消息）
- [x] 全仓 typecheck 通过；4522 已重启加载；未提交（等待 owner 指令）

## T19 LingWen 批次 H（响应式 + 编辑器排版）+ F21
- [x] H1 工作台 ≤900px「大纲｜编辑｜设定」切换（按列容器显隐）；书架 ≤600px 单列/浮层全宽/无横向滚动
- [x] H2 编辑器排版：字号 14/16/18、行距 1.6/1.8/2.0、专注模式；localStorage `lingwen.editor.prefs` 持久化
- [x] H3 修复 4 个直接子 panel 导致右栏折行：右栏包 `.right-column`，桌面恢复 260/560/300 三栏
- [x] 验证：`pnpm typecheck` 通过；清 `.next` 后 `pnpm build` exit 0；Playwright 25/25（三种视口 + 排版持久化 + 专注模式）
- [x] F21 `edit_file` 结果上限 64KiB→2MiB、`read_file` 硬上限 64KiB→4MiB 且大文件可读可分页；描述与提示同步
- [x] F21 单测：workspace-tools 13 passed（新增 >64KiB 读取/编辑 2 条）；chain-undo 9 + bubblewrap 5 passed；typecheck 通过
- [x] 4522 已重启加载 F21；3210 已重启加载新构建；未提交（等待 owner 指令）

## T20 LingWen 批次 I1（章节批量操作）+ F22/F23
- [x] 后端 `POST /api/books/[id]/chapters/batch`：delete / create-from-outline、事务、负增量、skipped、上限 200、400/404
- [x] 前端：章节/大纲复选框、全选、批量删除（confirm）、批量建章（已建章禁用）；旧单章功能保留
- [x] 验证：curl 覆盖 created/skipped/400/404/跨书；Playwright 14/14；book2 数据已恢复
- [x] F22 `buildFinishDiagnostics`：llm failure 原因置顶并写日志；新增单测（worker 20 passed）
- [x] F23 子代理提示：验证任务先跑门禁、stale `.next` 清理提示；prompt 单测 2 条（共 22 passed）
- [x] 全仓 typecheck 通过；4522 已重启加载 F22/F23；未提交（等待 owner 指令）

## T21 Demo Console 可观测 + 一键续写（F24/F25 + 批次 I2）
- [x] F24 `GET /demo/api/messages`：TurnOpened/AssistantMessageProduced → user/assistant；前端 2.5s 轮询渲染；输入上限 8000
- [x] F24 验证：脚本发消息后浏览器打开 4522 可见对话（Playwright）
- [x] F25 `resolveChildLlmTimeout`：`BUTLER_V5_LLM_TIMEOUT_MS` 覆盖（默认仍 30s），统一 loop 与 Effect.timeout；单测 4 例
- [x] I2 后端 `generate-batch`（NDJSON，1-5 章，无大纲 done created:0）；curl 验证 1345 字落库
- [x] I2 前端「一键续写」+ 取消/进度/并发禁用；Playwright 8/8，全流程 1552 字并清理
- [x] 对话修复取消提示两处：`signal.aborted || isAbortError`；notice 移到工作台顶部
- [x] 文档回填 spec §6.10；typecheck 通过、build 产物完整；未提交（等待 owner 指令）
