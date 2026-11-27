# Phase 7（v2 修订）— 用 WFXM Web 对话驱动真实仓库开发（Spec）

> 目标：在真实 GitHub 仓库 `XiaZiHunDun/LingWen` 上，**由 WFXM 自己**通过 Web 对话完成产品设计、编码、构建与 UI 验证，
> 以此暴露真实仓库开发闭环的缺陷，并据证据修复 WFXM 的 P0 问题。
> 约束：不自动 commit / push；GitHub 走 mihomo（`127.0.0.1:7890`）；生产配置不改动。

## 0. 为什么有 v2

| 版本 | 做法 | 结论 |
|------|------|------|
| v1 | 我直接手写 LingWen 的 Next.js 实现，并完成 build/烟测/UI 验证 | **作废**。违反「必须通过 WFXM Web 界面开发」的核心要求，验证的是我的编码能力而非 WFXM 闭环 |
| v2 | 用 WFXM 的 Web 对话入口驱动开发；我只做启动、只读核查、构建与浏览器验证 | 本文件 |

v1 的直写产物已备份并清空（`~/backups/LingWen-direct-impl-*.tar.gz`），不作为交付物。

## 1. 当前事实基线

- LingWen：分支 `WFXM`，工作区仅剩 `.git` + WFXM 通过控制台生成的半成品：
  `package.json`、`tsconfig.json`、`next.config.mjs`、`next-env.d.ts`、`.gitignore`、`pnpm-lock.yaml`、`node_modules`，
  `src/lib/{db.js,types.ts,chapters.js,outline.js,wordcount.js,llm.ts,prompts.ts}`。
  **无 `src/app`、无 API 路由、未 build。**
- WFXM 唯一 Web 对话入口：`scripts/demo-server.ts` 的 Demo Console。
- 已观测 WFXM 闭环缺陷（见 §3），证据来自 4522 进程 stdout。

## 2. 验收标准

| # | 验收项 | 判定方式 |
|---|--------|----------|
| A1 | 修复 §3 的 P0 缺陷 | 单测通过 + 4522 复跑无同类日志 |
| A2 | LingWen 的代码由 WFXM 通过 Web 对话产出 | 每轮 `POST /demo/api/chat` 的回复 + 工作区 diff 对照；我不得编辑 LingWen 源码 |
| A3 | `pnpm build` 通过 | LingWen 根目录执行，无类型错误 |
| A4 | 浏览器可用 | 构建后启动，浏览器验证书架页与 `/books/[id]` 三栏工作台 |
| A5 | 阶段报告 | 本文件 §6 记录实测结果、缺陷清单与证据 |

## 3. WFXM P0 修复（精确改动）

### F1 未知工具反复空转（`StartChildRun`）

- 位置：`packages/runtime/src/execution/conversation-loop.ts` 未知工具分支（约 451-470 行）。
- 现象：模型把决策标签当工具调用，连续 3 轮只收到 `[错误] 未注册的工具：StartChildRun`，耗尽轮次。
- 改动：
  1. 错误 tool result 追加可用工具名：`[错误] 未注册的工具：<name>。可用工具：<input.llmTools.join(", ")>。`
  2. 若 `<name>` 命中决策标签集合（`Respond` / `Finish` / `StartChildRun` / `WaitForApproval` / `CallCapability`），
     追加一句「这是决策标签，不是工具；启动子任务请调用 `delegate_to_subagent`」。
- 不改协议、不新增工具，只提升模型自纠成功率。

### F2 子代理「写完一个文件就收工」

- 位置：`apps/api/src/subagent-worker.ts` 子代理 system prompt（约 247-253 行）。
- 现象：子代理首轮写 1 个文件，次轮返回散文「已完成」；`decodeDecision` 报 `invalid JSON`，
  循环按纯文本 Respond 收尾，worker 把未完成任务记为成功。
- 改动：抽出并导出 `buildChildSystemPrompt(role, advertisedTools)`，prompt 明确：
  1. 需要动文件必须使用工具（原生 tool call），不要用文字描述代替；
  2. 只有任务目标全部落地后才允许用纯文本总结；
  3. 声明完成前必须用 `list_files` / `read_file` 核对目标文件真实存在；
  4. 工具名只能用列出的集合。
- 同时把纯文本提前收尾视为「未完成」：若本轮无 tool call 且 loop 仍有剩余迭代，
  prompt 已要求核对；不新增强制循环，避免死循环。

### F3 子代理轮次/工具预算偏小

- 位置：`apps/api/src/subagent-worker.ts:130`（`MAX_CHILD_ITERATIONS`）与其后传给 loop 的参数。
- 改动：`MAX_CHILD_ITERATIONS` 12 → 20；调用 `runConversationLoop` 时同时传 `maxIterations` 与
  `maxToolCalls`（同一数值），由 `resolveLoopIterations` 保证「至少一次工具/轮」。

### F4 失败回复不可诊断

- 位置：`apps/api/src/subagent-worker.ts` 子代理调用失败的 catch（约 555 行后）。
- 现象：父会话只看到「（子代理 developer 调用失败）」，无错误码、无最后一步。
- 改动：失败回复改为「子代理 <role> 失败：<错误码/原因>；最后一步：<traces 末 1-2 条>」，
  具体值走 `safeOwnerError` 与 loop 的 traces，不暴露堆栈与密钥。

### F5 任务文本截断（实测确认根因并修复）

- 根因：`packages/runtime/src/delegate-runtime.ts` 的 `TASK_PREVIEW_CHARS = 200` 被用在了
  **outbox payload** 上，而 `parseDelegateOutboxPayload` → `runChildLlm` 正是子代理读取任务的唯一来源；
  日志两次出现 `len=200` 即证据。
- 改动：outbox payload 的 `task` 改为全文；`goal` / step input 等元数据预览仍保留 200 字。
- 回归测试：`delegate-runtime.test.ts` 断言长任务在 outbox payload 中原样保留。
- 附：F2 补充运行时兜底（F2b）——工具型子代理在非最后一轮只回纯文本时，
  `conversation-loop` 最多 2 次注入「继续用工具落地」提示，而不是直接收尾。

### F6 主循环轮次固定 5，真实任务被迫「下一轮再做」（执行中新增，实测发现）

- 位置：`apps/api/src/wechat-inbound-butler.ts`（`maxIterations: DEFAULT_MAX_LOOP_ITERATIONS`）。
- 证据：M1 首轮 4 次工具调用后，第 5 轮（强制无工具收尾）返回「本轮只完成勘察，下一轮再补文件」；
  日志 `decodeDecision failed at iteration 4: invalid JSON`。
- 改动：新增 `resolveMaxLoopIterations(env)`，读 `BUTLER_V5_MAX_LOOP_ITERATIONS`（默认仍为 5）；
  4522 验证实例以 `BUTLER_V5_MAX_LOOP_ITERATIONS=18` 启动，生产默认不变。

## 4. 修复验证

- 单测：`packages/runtime/src/execution/conversation-loop.test.ts` 增加「未知工具错误含可用工具名」断言；
  新增 `buildChildSystemPrompt` 单测（含决策/工具约束关键字）。
- 命令：仓库根 `pnpm exec vitest run packages/runtime/src/execution/conversation-loop.test.ts <新测试>`；
  再跑受影响测试（`apps/api/src/wechat-dev-delegate.test.ts`）。
- 类型：按根 `package.json` 现有脚本执行（`typecheck` / `lint`，没有则跳过并记录）。

## 5. LingWen 里程碑（全部经 Web 对话驱动）

| 里程碑 | 对话目标（发给 WFXM 的需求） | 验收 |
|--------|------------------------------|------|
| M1 骨架 | 在现有半成品上补齐 `src/app` 最小页面与 `npm scripts`，确认可 build | `pnpm build` 通过 |
| M2 数据层 | 统一 `books/bible/outlines/chapters/llm_logs` 表结构与 `src/lib/repo` 访问函数 | 表可初始化，函数可被路由引用 |
| M3 API | books CRUD、bible、outline（JSON 模式）、chapters、`generate`（SSE/NDJSON 流式）、check、export | 路由文件齐全，类型通过 |
| M4 UI | `/` 书架 + `/books/[id]` 三栏工作台（大纲/章节、编辑器、设定与检查） | 页面渲染、交互可用 |
| M5 收口 | `pnpm build` + 启动 + 真实 LLM 烟测（建书→大纲→续写→检查→导出） | 浏览器验证通过 |

驱动规则：
1. 每轮只给一个可验证的小目标；回复里要求 WFXM 自己读文件、写文件、跑构建。
2. 我每轮只做只读核查（`git status`、文件清单、`Read`），发现偏差下一轮用对话纠正，不直接改 LingWen。
3. 子代理写文件路径必须落在 `BUTLER_V5_WORKSPACE_ROOT=/home/ailearn/projects/LingWen`。
4. 构建报错原文回贴给 WFXM，由它自己修。
5. 遇 `pending`（审批）按控制台提示处理后再继续。

## 6. 实测结果与缺陷清单（执行后回填）

### 6.1 里程碑实测（全部经 `POST /demo/api/chat` 驱动）

| 里程碑 | 对话轮次 | 结果 | 关键证据 |
|--------|----------|------|----------|
| M1 骨架 | 1 | `src/app` 3 文件，build 通过 | 4 个静态页 |
| M2 数据层 | 2 | `db.js` 五表 + `repo.js` 14 导出，`tests/db.test.mjs` 8 passed | `pnpm test` |
| M3 API | 6（books→bible→outline→chapters→generate→check+export） | 10 个路由全部生成，`pnpm build` 通过 | build 路由表含 10 个 `ƒ /api/*` |
| M4 UI | 3（书架→两栏工作台→三栏+AI 流式+体检）+ 1 次被拒 | 书架与 `/books/[id]` 三栏工作台可用 | Playwright 断言见 6.3 |

- 对话轮次总计 12（含 1 次因输入超长被直接拒绝，未消耗子代理）。
- 每轮我只做：发需求、读文件核查、跑 `pnpm typecheck` / `pnpm build`、起服务、跑 API 与浏览器验证；**未手改 LingWen 任何源码**。

### 6.2 真实仓库闭环新增缺陷（按优先级）

| 级别 | 缺陷 | 证据 | 状态 |
|------|------|------|------|
| P1 | Demo Console 单条消息硬上限 2000 字符，超长直接拒收且不截断/不提示拆包；真实项目的详细规格必须人工拆成多轮 | M4-2 回复：「消息过长（2498 字符，上限 2000）。请发具体需求。」 | 待修 |
| P1 | 对话 API 在父代理 `Respond` 后立即返回 `ok:true`，子代理仍在后台写文件；调用方无法判断任务真正完成，只能轮询工作区 | M3-1..M3-6 每次 `/demo/api/chat` 均返回「已转到后台继续处理」，而文件在数分钟后才出现 | 待修（需要完成事件/任务状态查询） |
| P1 | `E-LLM-01` 间歇失败仍会命中父代理决策轮；失败回复不携带「子任务是否已落盘」，恢复只能靠人工核对 | M4-2b 回复 `[E-LLM-01 · turn-179]`，但子代理实际已写完全部代码 | 部分缓解（F4 只覆盖子代理失败） |
| P2 | 主代理工具集没有 `list_files`/glob，模型自述「我没有 list_files」，无法按 prompt 要求核对文件存在 | M3-1 回复原文 | 待修 |
| P2 | 子代理按轮追加 CSS 时重复定义 `.workspace-grid`，依赖后定义覆盖生效；闭环缺少「生成后自审 diff/lint」步骤 | `globals.css` 两处 `.workspace-grid` | 观察项 |
| P2 | 父代理直接调用 `edit_file` 触发审批后，恢复的续跑预算不足以完成剩余步骤，只能回「部分完成，本轮不能再调用工具」；需人工再发一轮「继续」 | E2-1：批准后仅落地 51 行 helper（162-212 行），面板需第二轮补齐 | 已修（F15：写类审批保留 exec 工具并按 env 续跑；`edit_file` 归入 exec 画像后 dev_task 改走委派） |

### 6.3 收口验证（真实 LLM 烟测 + UI）

- 构建：`pnpm build` 通过，路由表含 `/`、`/books/[id]`、10 个 `ƒ /api/*`。
- 服务：`next start -p 3210`（LLM 用 DeepSeek OpenAI 兼容端点，仅进程环境变量，未写入仓库）。
- API 烟测：建书 → 加设定 → LLM 生成 3 章大纲 → 建章节 → `generate` 流式返回 1165 字节 → 落库 `wordCount=334`、`status=drafted` → `check` 返回 stats/issues → `export?format=md` 带 `Content-Disposition`。
- UI（Playwright + 本机 headless Chromium）：书架 1 本《长夜将至》；工作台 3 栏、3 条大纲、1 章、1 条设定；点击章节后编辑器载入 399 字正文；体检面板返回「大纲覆盖率偏低」。
- 内置浏览器桥接（Agent 与 Skill 两条路径）访问 `127.0.0.1:3210` 均超时，改用本机 Chromium 完成验证；该环境问题已记录为验证通道限制。

### 6.4 第二轮：闭环缺陷修复（F7–F13）

| 编号 | 缺陷（实测触发的现象） | 修复 | 验证 |
|------|------------------------|------|------|
| F7 | 模型把工具名猜成 `list_files`，主代理只会回「可用工具：list_dir」，不会联想 | 未知工具错误增加 Levenshtein 近似名提示（≥0.6 相似度） | 单测：`list_files` → 「你是不是想用 list_dir」 |
| F8 | Demo Console 输入上限 8000，但 spam guard 仍按 2000 拒收长规格（M4-2 被拒） | `BUTLER_V5_SPAM_MAX_CHARS` 可配置；Demo 启动自动对齐 8000；错误文案改为「请拆成多段或精简后重发」 | 1500 字消息可正常处理；单测覆盖默认/覆盖/非法值 |
| F9 | 父代理失败回复不提示「子任务可能仍在后台」 | 失败信封追加一行后台任务提示 | 单测（error-codes 10 passed） |
| F10 | `/demo/api/chat` 父代理 Respond 即返回 `ok:true`，子代理仍在跑，只能轮询文件 | 子代理 worker 增加 `onEvent`；Demo 新增 `GET /demo/api/status`（busy/delivered/lastEvent/lastError），chat 返回 `statusUrl`/`workerBusy` | 实测提交后 status 显示 busy=1，空闲后归零 |
| F11 | 父代理回「已派子代理」但 0 次工具调用，任务根本没启动（B-2 首次） | `delegationClaimGuard`：非末轮纯文本声称已委派时注入一次纠正提示 | 单测 + 重启后 B-2 正常委派（toolCalls=9） |
| F12 | 子代理重复执行同一命令（`pnpm typecheck`）被 stuck-loop 阈值 3 误杀 | 子代理 `stuckLoopThreshold=6`；prompt 明确「同一命令不超过两次、失败先读报错」 | C-1b 重试成功 |
| F13 | `read_file` 无分页，整读 37KB 页面文件导致子代理第 1 轮即失败 | `read_file` 支持 `offset/limit`，输出上限 24KiB 并提示分页；工具 schema/提示同步 | 单测 2 条：分页读取、超限截断 |
| F14 | 只有整文件 `write_file`：改 1600 行页面里几行也要重写全文，导致整文件覆盖丢功能（A-2a 书籍设置/↑↓ 被覆盖）、输出超限与上下文耗尽 | 新增 `edit_file(path, oldText, newText, replaceAll?)`：唯一片段替换、多处匹配拒绝、未命中文案提示先 read；接入 capability allowlist/pregrant/审批/提示词 | 单测 3 条（唯一替换、多处拒绝+replaceAll、缺失提示）；E1/E2 实测子代理用 edit_file 增量改 page.tsx（+234 行，0 删除） |
| F15 | 审批恢复后续跑预算固定 5 轮，且写类能力审批后立刻回「✅ 已写入」不再续跑；E2-1 批准 edit_file 后只回「本轮不能再调用工具，仅部分完成」 | 写类审批（write_file/edit_file）恢复后保留 exec 工具并续跑，轮次读 `BUTLER_V5_MAX_LOOP_ITERATIONS`；`run_command`/失败 exec 仍只保留只读工具；`edit_file` 同步纳入 exec 工具画像、dev session 授权、intake 判定与 dev 校验 | 单测 3 条（写类保留工具、命令不保留、轮次继承 env）；typecheck + 相关 93+91 测试通过 |
| F16 | `run_command` 默认 5s 超时，子代理执行 `pnpm build` 被中途杀掉，无法完成构建自检 | 新增 argv 感知超时：pnpm/npm/yarn/npx/next/node/python3 等长任务 120s，其它命令仍 5s；显式 `BUTLER_V5_RUN_COMMAND_TIMEOUT_MS` 优先；能力注册表在调用时按 args 计算超时 | 单测：`pnpm build`/`node --test` → 120s，`ls`/无 argv → 5s；slirp/env 覆盖用例保持通过 |
| F17 | 父代理已派出子任务并在后台运行时，失败信封仍以「处理失败，请稍后再发一次」开头（本轮 E1 实测），诱导 owner 重发造成重复执行 | 信封支持 `delegated`/`toolCalls` 上下文：已委派 →「任务已交给后台执行…不要原样重发」；已执行工具 →「处理中断，已有 N 次操作，可能部分生效」；`edit_file` 审批 resource 改用文件路径，不再显示会话 id | 单测 2 条信封分支 + `resourceForTool("edit_file")` 断言；相关 57 测试通过 |
| F18 | 子代理 `pnpm build` 超时后只杀直接子进程，`sh -c next build` 与 node 变成孤儿继续写 `.next`；后续构建长时间挂起且无任何日志（本轮实测同时残留 4 个孤儿构建进程） | `spawnCaptured` 在 POSIX 下 `detached: true` 让子进程自成进程组，abort 时 `kill(-pid, SIGKILL)` 整组回收，失败再退回单进程 kill | 新增单测：父进程派生 30s 孙进程，1.5s 超时后孙进程 PID 已不存在（workspace-tools 11 passed） |
| F19 | 工具额度用尽后仍注入「任务还没完成，请继续调用工具」（F2b），与「不要再调用工具」自相矛盾；模型连续 3 轮只能回纯文本，浪费 2 次 LLM 调用，且子代理回「工具额度已用尽」被父代理判为未完成而整单重派一次 | 额度用尽时跳过 tool-first 与 delegation-claim 提示，直接接受模型的纯文本总结 | 单测：`maxToolCalls=1` 后纯文本总结不再触发 nudge，`toolCalls=1`、`finalDecision=Respond`（conversation-loop 29 passed） |
| F20 | 子代理 LLM 传输失败（`socket hang up`/超时）时直接回「（子代理 developer 调用失败）」，而本轮只读过文件、零改动；owner 只能人工重发，且重发即重复执行 | 子代理结束若为 `llm failure` 且 trace 中无 `write_file`/`edit_file`，worker 自动重跑一次子任务；有写操作则不重试，避免重复落盘 | 新增单测：首次 complete 失败、第二次成功 → 父会话收到重试后的回复且 complete 调用 ≥2（subagent-worker 19 passed）；同时修正 2 条既有测试对「最后一条消息即 tool 结果」的错误假设（预算提示会追加 system 消息） |

### 6.5 第二轮：LingWen 产品完善（全部经 Web 对话）

| 批次 | 内容 | 验证 |
|------|------|------|
| A 数据完整性 | 书籍设置编辑、章节删除、↑↓ 排序、大纲手工编辑、按大纲建章、`/api/stats` 全局统计 | typecheck/build；API 烟测 PATCH/DELETE/seq/outline manual 全部 2xx |
| B AI 写作 | `generate` 注入本章大纲 + 600 字衔接上文；新增 `POST /api/chapters/[id]/review`（JSON 问题清单）；生成可中止（AbortController）；生成/检查互斥 | 真实 LLM：review 返回结构化 issues；生成流式可用 |
| C 体验 | 1.5s 防抖自动保存、Cmd/Ctrl+S、beforeunload 保护、书架统计条 | Playwright：出现「已自动保存 10:22:32」，统计条「作品 1 · 章节 1 · 总字数 342」 |
| D Agent 化 | `POST /api/books/[id]/assist` 流式创作助手（书籍+设定+大纲+选中章节上下文）；右栏对话面板 | Playwright 实际提问并收到流式回答 |
| E 版本历史 | 章节快照表 `chapter_revisions` + repo 五个函数 + 3 个路由；PATCH 自动存 manual、generate 收尾存 generate、恢复前存 pre-restore；编辑器「历史版本」面板（列表/只读预览/二次确认恢复） | typecheck/build 通过；API 烟测：新增 manual 快照、pre-restore 快照、restore 回滚正文、非法 id 404；Playwright：面板 4 条版本、只读预览、恢复后正文回退且旧功能按钮仍在 |

- 回归发现：A-2a 的部分改动被后续整文件写入覆盖（设置面板与 ↑↓ 丢失）。已通过对话补回，并在验证脚本中固定检查「AI 检查 / 创作助手 / 自动保存 / 书籍设置」四项均存在。
- 复测：`pnpm build` 通过（16 条路由）；WFXM 侧 62 个相关单测通过；3210 服务在线。
- 仍未提交：等待 owner 指令。

### 6.6 第三轮：JSON 备份/恢复 + 全局搜索（批次 F，全部经 Web 对话）

| 批次 | 内容 | 验证 |
|------|------|------|
| F1 JSON 备份/恢复 | `GET /api/books/[id]/export/json`（version=1 快照：book/bible/outlines/chapters，不导出 id 与 llm_logs）；`POST /api/books/import/json`（version/title/chapters 校验、事务写入、outline 旧新 id 映射、重名自动加「（导入）」、wordCount 缺失按正文重算） | typecheck/build 通过（24 条路由）；curl：导出 3123 B / 404 正常；导入 201 返回新 id；version=2 与空标题均 400；导入后书 2 章节 1、字数 350、大纲 3、设定 1，与原书一致 |
| F2 全局搜索（后端） | `GET /api/search?q=&limit=` 跨 chapters/outlines/bible（LIKE + ESCAPE 参数化、JOIN books 过滤孤儿、snippet 命中点前后各 40 字、limit 默认 20 上限 50、`total` 为真实命中总数） | curl：`q=红笔` total=10、空 q 返回空、`q=%` 转义后 0 命中；build 通过含 `/api/search` |
| F2 全局搜索（UI） | 书架顶部搜索框（300ms 防抖、浮层列表、Esc/点外关闭、无结果文案、过期响应丢弃）；点击章节结果跳 `/books/{id}?chapter={cid}`；工作台首次加载按 `?chapter=` 自动选中章节 | Playwright：输入「红笔」出 10 条 → 点首条跳 `/books/2?chapter=3` → 编辑器载入 423 字且含关键词、章节高亮；无结果文案命中；书籍设置/AI 检查/历史版本/创作助手/新建章节仍在 |

- 本轮对话轮次 3（F1 后端、F2 后端、F2 前端+跳转），未手改 LingWen 源码。
- 新暴露的 WFXM 缺陷：F18（超时只杀单进程→孤儿构建阻塞后续构建）、F19（额度用尽后仍 nudge 且导致整单重派）；均已在 §6.4 修复并补单测，4522 已重启加载。

### 6.7 第四轮：备份入口 / 润色 / 写作日历（批次 G，全部经 Web 对话）

| 批次 | 内容 | 验证 |
|------|------|------|
| G1 备份入口 | 书架「导入 JSON」（隐藏 file input → 前端解析 → POST import，成功提示并刷新）、书卡与设置面板「导出 JSON」；搜索浮层键盘导航（↑↓ 循环、Enter 打开、Esc 关闭、悬停同步高亮、scrollIntoView） | Playwright：导入后列表 +1 且出现「已导入《界面导入测试》」；↓ + Enter 跳 `/books/1?chapter=1`，编辑器 423 字；详情页 1 个「导出 JSON」 |
| G2 章节润色 | `POST /api/chapters/[id]/polish` 流式（polish/condense/expand + 额外要求，上下文含正文/大纲/设定，不落库、写 llm_logs）；工作台「润色」+ 预览面板 + 应用（PATCH 自动快照）+ 撤销（revisions 恢复）+ 取消 | 真实 LLM：流式返回全文；Playwright：预览可应用（423→399 字），撤销后回到 423，AI 检查/历史版本/书籍设置仍在 |
| G3 写作日历 | 迁移新增 `writing_sessions` / `app_settings`（幂等，兼容旧库）；repo 增加 recordWritingDelta / dailyWordCounts / getDailyGoal / setDailyGoal；PATCH 记净增字数；`GET /api/stats/daily`、`PUT /api/settings/daily-goal`；书架今日进度条 + 14 天柱状图 + 点击设目标 | 已有库平滑迁移；curl：daily 结构正确、goal=1200/非法 400、PATCH 后当日 -330；Playwright：14 根柱、点目标可保存 |
| G4 口径修复 | 恢复版本按「恢复后-恢复前」记账；删除章节记 -字数；对外字数与柱高 clamp ≥0、百分比 0..100；新增 `tests/writing-stats.test.mjs`（聚合跨天 0 填充、负值不返回为负、目标边界） | pnpm test 11 passed；受控实测：PATCH +80、restore -80 均入库；书架由「-330 字（-28%）」变为「今日 0 / 目标 900 字（0%）」 |

- 本轮对话轮次 4（G1/G2/G3/G4），另有 1 次因子代理 LLM 传输失败未落地（G4 首次），重发后完成；该失败直接促成 F20。

### 6.8 第五轮：窄屏响应式 / 编辑器排版（批次 H）+ F21

| 批次 | 内容 | 验证 |
|------|------|------|
| H1 响应式工作台 | ≤900px 顶部「大纲｜编辑｜设定」切换条，按列容器单面板显示；≤600px 书架书卡单列、搜索浮层全宽、按钮换行、无横向滚动 | Playwright（800px）：默认只显示编辑列，切换三列互斥；右栏 4 个板块（润色/设定集/体检/创作助手）全部可见；390px 书架 `scrollWidth=clientWidth=390`、`.book-grid` 单列 |
| H2 编辑器排版 | 字号 14/16/18、行距 1.6/1.8/2.0、专注模式（隐藏两侧列、可一键退出）；localStorage `lingwen.editor.prefs` 持久化 | Playwright：默认 16px → 选 18px/2.0 后 `font-size:18px`、`line-height:36px`；localStorage 命中；刷新后仍为 18px/2.0；专注模式只剩编辑列且退出恢复 |
| H3 三栏布局回归 | 修复 `.workspace-grid` 直接子元素为 4 个 panel 导致右栏第 2 个 panel 折行到左下 260px：右栏改为单个 `.right-column` 容器，桌面端严格三栏 | Playwright：3 个子元素同一行，宽度 260/560/300；右栏标题顺序 润色→设定集→体检→创作助手；`pnpm typecheck` 通过、`pnpm build` 通过（25 条路由） |

#### F21 edit_file/read_file 的 64KiB 硬上限（本轮实测暴露）

| 项 | 内容 |
|----|------|
| 现象 | 工作台 `page.tsx` 达 82KB 后，子代理无法用 `edit_file` 修改（`edited file exceeds 65536 bytes`），也不能整文件 `read_file`（`file exceeds 65536 bytes`，`offset/limit` 同样先被拒）；它改用 `node -e` 临时 patch 脚本改文件，绕过唯一片段校验与 undo 快照 |
| 根因 | `MAX_WRITE_BYTES=64KiB` 被同时用于 `write_file` 的入参与 `edit_file` 的**结果文件大小**；`read_file` 的 64KiB 判断在分页之前 |
| 修复 | `edit_file` 结果上限改为 `MAX_EDIT_RESULT_BYTES=2MiB`；`read_file` 硬上限改为 `MAX_READ_FILE_BYTES=4MiB`，超出仅提示用 `run_command` 分段，64KiB~4MiB 直接按 24KiB 分页返回；工具描述与主代理提示同步 |
| 验证 | 新增单测 2 条（>64KiB 文件可读、可分页、可 edit）；`workspace-tools.test.ts` 13 passed、chain-undo 9 + bubblewrap 5 passed；全仓 typecheck 通过；4522 已重启 |

#### 本轮观察（未单独修）

- 一次需求触发 3 个 developer 子任务：首个因 `run_command` 诊断失败→F20 自动重试成功，随后父代理又自派了两次“验证”任务，第二个验证任务把工具额度耗尽并回报“额度用尽”。任务已完成后反复自派验证仍会浪费预算，暂记为观察项。
- `pnpm build` 在被上次超时击杀的 `.next` 污染后会「编译成功但不退出」（timeout 124，产物与路由表完整）；`rm -rf .next` 后 exit 0。子代理需要用 `node -e` 清理（`run_command` 白名单没有 rm），建议后续评估是否提供安全的缓存清理手段。

### 6.9 第六轮：章节批量操作（批次 I1）+ F22/F23

| 批次 | 内容 | 验证 |
|------|------|------|
| I1 后端 | 新增 `POST /api/books/[id]/chapters/batch`：`delete`（事务内逐条删、按正文字数记负增量、跨书/不存在计 skipped）/ `create-from-outline`（按大纲建空章、seq 递增、已建章大纲跳过、返回新 id）；单次上限 200、id 去重、非法 action/数组 400、书不存在 404 | curl：`create [8,9] → {created:2, ids:[6,7]}`；重复 → `{created:0, skipped:2}`；`delete [6,7,999,6] → {deleted:2, skipped:1}`；非法 action/`[0,-1]` 均 400；书 9999 404；跨书 id → skipped |
| I1 前端 | 章节列表复选框 + 全选/取消 + `批量删除（已选 N）`（confirm 二次确认）；大纲列表复选框 + `批量建章（已选 N）`（已建章大纲禁用）；旧单章删除/↑↓/按大纲建章保留 | Playwright 14/14：3 章全选→取消 1 条→批量删 2 条后只剩「红笔」且选择清零；勾选大纲「空号」建章成功后列表 +1；旧 ↑↓ 按钮仍在；800px 大纲 tab 复选框可用；清理后 book2 恢复 1 章 |

#### F22 失败诊断丢失 LLM 失败原因

| 项 | 内容 |
|----|------|
| 现象 | 子代理失败回复只显示「（诊断：read_file@6: …）」，看不到 `llm failure:` 原因；排查只能靠猜 provider 还是模型 |
| 根因 | `traces.slice(-2)` 取最后两条，通常是两次工具调用，`llm failure: …` 排在它们之前被裁掉；日志又只打印回复前 80 字 |
| 修复 | 抽出 `buildFinishDiagnostics(finalDecision, traces)`：`llm failure:` 置顶 + 最后一条工具 trace；命中时 `logger.warn` 输出失败详情（前 300 字） |
| 验证 | 新增单测（失败原因在工具 trace 之前、非 Finish 返回空）；subagent-worker 20 passed |

#### F23 验证类子任务把预算花在读文件上

| 项 | 内容 |
|----|------|
| 现象 | 父代理派出的「验证」子任务连续 `read_file`/`run_command` 读大文件，20 次工具预算耗尽后回「无法再执行 pnpm build」，父代理只能再派第三个任务 |
| 修复 | 子代理提示新增两条：验证/自检任务先直接跑 `pnpm typecheck` / `pnpm build` 再看文件；`pnpm build` 已输出 `Compiled successfully` 后仍不退出（stale `.next`）时用 `node -e` 清理 `.next` 再重试一次 |
| 验证 | prompt 单测新增两条断言；subagent-worker-prompt 2 + subagent-worker 20 passed；4522 已重启 |

#### 本轮观察

- 一次需求触发 3 个子任务：首个失败两次（F20 重试后仍失败）→ 父代理整单重派；第二个验证任务预算耗尽未跑 build → 父代理再派第三个。任务已完成时父代理仍会自派验证，建议后续评估「完成信号 + 单任务验证上限」。
- 第三个任务实际完成了构建（`.next/BUILD_ID` 与 `chapters/batch` 路由产物齐全），但 `pnpm build` 仍在 120s 被杀；这是 stale `.next` 导致的退出挂起，不是编译失败。

### 6.10 第七轮：Demo Console 可观测（F24/F25）+ 一键续写（批次 I2）

| 批次 | 内容 | 验证 |
|------|------|------|
| F24 会话可观测 | 新增 `GET /demo/api/messages`（把 `TurnOpened`/`AssistantMessageProduced` 投影为 user/assistant 消息，最多 60 条、单条 6000 字）；前端每 2.5s 轮询渲染，任何客户端（脚本/浏览器）发起的对话都能看到；输入上限同步 8000 | Playwright：脚本 `POST /demo/api/chat` 后，浏览器直接打开 4522 即渲染「你好」与回复气泡；`/demo/api/messages` 返回 role/content/at + worker 状态 |
| F25 子代理 LLM 超时 | 子代理把 `llmTimeoutMs` 硬编码 30s，大上下文下必现 `llm failure: LLM timeout after 30000ms`（F22 日志实锤），重试同样超时 | 新增 `resolveChildLlmTimeout(env)`：读 `BUTLER_V5_LLM_TIMEOUT_MS`，默认仍 30s；`Effect.timeout` 与 loop 参数统一取值；单测 4 例（默认/env/0/非法）；4522 以 120s 启动后同一 I2 任务不再超时 |
| I2 后端 | `POST /api/books/[id]/chapters/generate-batch`：未建章大纲按 seq 取前 N（1-5），建空章→流式生成→落库，NDJSON 事件 start/delta/chapter-done/done/error；无大纲返回 `done created:0` | curl：book2 `count=1` → 新章 1345 字、`{"type":"done","created":1}`；数据清理后恢复 |
| I2 前端 | 大纲列「一键续写接下来 N 章」：数字输入（默认 1）+ 开始/取消；NDJSON 实时进度；生成中禁用单章生成与批量按钮 | Playwright 8/8：进度文本出现→取消→提示「已取消续写（已生成的章节已保存）」→按钮恢复；全流程跑通后提示「一键续写完成，共 1 章」且章节 1552 字 |

#### 本轮由对话修复的两个前端缺陷（经 WFXM 连续两轮纠正）

| 问题 | 根因 | 修复 |
|------|------|------|
| 点「取消」后无任何提示 | abort 触发的是 `TypeError: Failed to fetch`，`isAbortError` 只认 DOMException.AbortError，走了 `setBatchError`；且循环后的 `signal.aborted` 分支到不了 | catch 判定改为 `controller.signal.aborted || isAbortError(err)`，沿用 `cancelNotified` 去重 |
| 修正判定后仍看不到提示 | `.notice` 渲染在 `selectedChapter === null ? 空态 : 编辑器` 的 else 分支内，未选章节时整块不渲染 | 把 notice 提升到工作台顶部（workspace 头部下方），任何面板/选中状态都可见 |

#### 本轮观察

- 一条「补提示」需求触发 8 个子任务（含父代理自派的多轮验证），耗时显著；完成信号与验证上限仍是下一优先级。
- 客户端取消后服务端仍会把当前章写完并落库，期间旧服务日志出现 `failed to pipe response / ERR_INVALID_STATE`；建议路由在写入下一段前检查 `req.signal.aborted`，尽早止损。
- `pnpm build` 退出挂起仍偶发（同一个干净 `.next`，一次 exit 0、两次 timeout 124 但产物完整）；F23 的提示可缓解，但根因仍在 Next 进程句柄。

### 6.11 第八轮：写作日历月视图（批次 J）

| 内容 | 验证 |
|------|------|
| 后端 `GET /api/stats/month?month=YYYY-MM`：`monthlyWordCounts` 按本地月聚合 `writing_sessions`（负数按 0），返回 `{month, days, total, activeDays, bestDay}`；缺省当月、格式非法 400 | curl：2026-11 → 30 天、total 0；2026-10 → 31 天且首尾日期正确；`2026-13`/`abc` → 400 |
| 书架新增月视图：7 列周一到周日、按月补齐空格、日号+字数、四级着色；上一月/下一月切换；「连续写作 N 天」（90 天窗口，今天为 0 则从昨天起算）；目标达成显示「今日目标已达成」，未达成显示「还差 X 字」；14 天柱图保留 | Playwright 11/11：默认收起 → 展开 30 格 → 上一月 31 格 → 回到当月 → 收起；`cal-streak`/`cal-goal` 文案正确；书架 2 本书仍在 |
| 构建 | 清 `.next` 后 `pnpm typecheck` 通过、`pnpm build` exit 0，路由表含 `ƒ /api/stats/month` |

#### 本轮观察

- 父代理自派验证的行为仍在：本轮一条需求期间 `startedTasks` 从 2 增长到 10，验证任务重复读取同一批文件；F25 生效后未再出现 `LLM timeout`。

### 6.12 第九轮：客户端断开止损（批次 K）+ F26

| 内容 | 验证 |
|------|------|
| LingWen `generate-batch` / 单章 `generate` / `llm.ts` 接入 `req.signal`：写事件前检查 `aborted`，断开后停止后续章节；`isStreamClosedError` 吞掉 `ERR_INVALID_STATE`；保留当前章已写入内容 | `timeout 6 curl -N` 发起 `count=3`：流在 6s 被切断后只新增 1 章（9 字，未继续第 2/3 章）；新进程 stdout 中 `ERR_INVALID_STATE`/`failed to pipe` 均为 0；`typecheck` 通过、clean `build` exit 0；书架 Playwright 11/11 回归 |
| F26 子代理自测数据清理 | K 的自测在演示库留下 `自测大纲4/5/6`（outlines 12-14）与章节 22-25，父代理未发现也未清理。子代理提示新增第 11 条：自测优先用临时书/临时记录并删除，无法清理必须在回复列出残留 id 与表名（prompt 单测 2 passed）；演示库已用 API 恢复（outlines 重建为 15-17、章节仅保留 id=3） |

#### 本轮观察

- 服务端断开止损生效后，日志噪声消失，但「当前章仍会写完」是保留语义（已明确写入需求）。
- `GET /demo/api/messages` 只能看到**当前进程**的会话：重启 4522 后 `conversationId=null`、历史为空。若需要跨重启查看，需要把 demo 的事件存储落到 SQLite。

### 6.13 第十轮：委派纪律（F27）+ 编辑器状态栏（批次 L）

| 内容 | 验证 |
|------|------|
| F27 主代理提示新增 Delegation discipline：一个 owner 需求最多派发 2 个子任务；派发成功后先回「已在后台处理」并结束本轮；子代理回复到达后再判断下一步；仅核对刚完成的工作时自己跑 1-2 条命令 | 单测 5 passed（prompt 断言）；实测一条功能需求 `startedTasks` 从上一批的 3-12 降到 **2**（1 实现 + 1 验证） |
| LingWen 编辑器状态栏：`本章 N 字`（实时）、有选区时 `已选 N 字`、保存状态 `已保存/未保存/保存中/保存失败` 与自动保存联动（`saveState` 状态机） | Playwright 8/8：默认 407 字/已保存 → 输入 5 字变 412/未保存 → 自动保存回已保存 → Shift+→ 选中 3 字显示「已选 3 字」→ 还原后 407 字；`typecheck` 通过、clean `build` exit 0 |

#### 本轮观察

- `setSelectionRange` 不会触发浏览器的 select 事件，React 的 `onSelect` 收不到；Playwright 必须用键盘（Home + Shift+ArrowRight）才能验证选中字数。这不是实现缺陷，后续脚本按键盘操作。
- F27 是提示词级约束，单样本有效；若后续仍出现 >2 次派发，需要升级为循环内的硬上限（`maxDelegationsPerTurn`）。

### 6.14 第十一轮：F27 硬上限 + 编辑器保存时间（批次 M）

| 内容 | 验证 |
|------|------|
| F27 硬上限：`ConversationLoopInput.maxDelegationsPerTurn`；`runButlerLoop` 读 `BUTLER_V5_MAX_DELEGATIONS_PER_TURN`（默认 2，0 关闭）；超出后拒绝新的 `StartChildRun` 决策或 `delegate_to_subagent` 原生工具调用，并注入「请汇报并结束本轮」系统消息 | 单测：决策路径 + 原生工具路径各 1 条（4 次派发 → 只执行 2 次，traces 含 `delegation-cap`）；`resolveMaxDelegationsPerTurn` 5 组用例；conversation-loop 31 passed、butler 30 passed |
| 实测发现并修复：只守 `StartChildRun` 决策路径时，模型走原生 `delegate_to_subagent` 工具调用仍可在一轮派发多个子任务（cap=1 实测 `startedTasks=2`） | 补上原生工具路径守卫后重启 4522（cap=1），同一规模需求 `startedTasks=1`、`invoking LLM` 仅 1 次，且任务正常完成 |
| LingWen：编辑器顶部「最后保存：HH:MM:SS / 尚未保存」（保存成功时更新）；书架页脚「LingWen v0.1.0」 | Playwright 4/4：页脚版本号、初次「尚未保存」、状态栏仍显示 407 字/已保存、输入后自动保存并更新时间 |

#### 本轮观察

- 派发上限必须同时覆盖两条路径（决策标签 + 原生工具调用），只改其中一条会被真实模型绕过；这是「同一语义两套入口」的典型陷阱。
- cap=1 的实测显示：父代理在一轮内确实会连续两次调用 `delegate_to_subagent`，硬上限是必要的，而非仅靠提示词。

### 6.15 第十二轮：历史版本并排 diff（批次 N）

| 内容 | 验证 |
|------|------|
| LingWen 历史版本面板新增「对比当前 / 退出对比」：手写行级 LCS（`Uint32Array` DP + 回溯对齐），左栏历史版本删除行标红 `diff-del`、右栏当前正文（含未保存改动）新增行标绿 `diff-add`，对侧渲染占位行保证左右严格对齐；顶部 `+N 行 / -M 行`，任一版本超过 2000 行时只比前 2000 行并提示；`≤600px` 两栏改单列 | `pnpm typecheck` 通过；`rm -rf .next && pnpm build` exit 0（`/books/[id]` 15.4 kB）；重启动 3210 后 Playwright 14/14（版本列表 6 条、两栏各 18 行对齐、`+1 行 -1 行`、恢复/关闭预览按钮仍在、退出对比回到只读预览、编辑器与 AI 生成区正常、0 控制台错误）；390px 视口 `gridTemplateColumns` 单列、两栏纵向堆叠、`scrollWidth=390` 无横向溢出 |
| 数据零污染 | 全程未发写请求；验证后 `GET /api/chapters/3/revisions` 仍为 6 条、`/api/books/2/chapters` 仍为 1 章 |

#### 本轮观察

- F27 硬上限生效：一条完整前端需求 `startedTasks=1`，子代理自己跑完 typecheck + build 并回报，未再出现「父代理自己动手」或跨轮重复派发。
- 子代理在运行中的 3210 上执行 `pnpm build`，会替换 `.next` 但不会热更新已启动的 `next start`；验证前必须重启 3210（本轮按「停止 → clean build → 重启」执行）。这是 Next.js 部署语义，非闭环缺陷。
- 演示机 `.env` 内含 `PATH`（指向 node v20），直接用 `set -a; . .env` 会把当前 shell 的 node 切到旧版本导致 `pnpm` 报语法错误；启动 3210 时只提取 `DEEPSEEK_*` 两个值。

### 6.16 第十三轮：独立写作统计页 `/stats`（批次 O）

| 内容 | 验证 |
|------|------|
| LingWen 新增 `/stats`：概览卡（作品数/章节总数/总字数/今日字数÷日目标带进度条，超目标封顶 100%）、近 14 天柱状图（今天高亮 + 峰值标注 + 全 0 空态）、作品对比（并发拉每本 `/api/books/[id]/stats`，按总字数降序，横向条按最大值归一化）、本月小结（累计/活跃天数/最佳日/连续天数）；书架顶部加「写作统计」入口 | `pnpm typecheck` 通过；`rm -rf .next && pnpm build` exit 0；重启 3210 后 Playwright **21/21**：入口跳转、4 卡数值与 `/api/stats` 一致、进度条 `aria-valuenow` 与公式一致、14 根柱且末根为今天、峰值标注、对比行按 353→350 降序且首条 100%、月汇总与 `/api/stats/month` 一致、返回书架可用、0 控制台错误；390px 无横向溢出且概览卡换行 |
| 复用而非新增 | 页面只读 `/api/stats`、`/api/stats/daily?days=90`、`/api/stats/month`、`/api/books`、`/api/books/[id]/stats`，未新增后端路由、未改数据库、未引三方库；连续天数用 90 天窗口从今天回溯，口径与书架一致 |

#### 本轮观察

- 子代理这次主动核对了「连续天数口径」和 `days` 查询参数是否存在（确实支持 `?days=90`），说明 F2/F23 的「完成前核对」提示在真实任务上生效。
- 一条需求触达 2 个子任务（实现 + 补充），正好卡在 F27 默认上限 2，未被截断，也未出现重复执行。
- `todayWords` 只有 3 字，进度条显示 0%，是四舍五入后的正常结果；验证脚本用同一公式断言，不靠肉眼。

### 6.17 第十四轮：章节状态 draft/final（批次 P）+ F28/F29

| 内容 | 验证 |
|------|------|
| LingWen 章节状态落地：`normalizeChapterStatus` 纯函数（空值→draft、仅接受 draft/final、其它→null）；`PATCH /api/chapters/[id]` 传非法 status 返回 400 且不落库；GET 列表/详情空值统一输出 draft；单章与批量建章默认 draft；章节项加「草稿/定稿」徽章（`stopPropagation` + PATCH + 就地更新 + notice），工具条加「只看未定稿」开关（筛选不清空编辑器） | `pnpm typecheck` 通过；`pnpm test` 15/15；clean `pnpm build` exit 0；Playwright **18/18**：非法值 400、默认草稿、点徽章切定稿且编辑器内容不变（423 字）、落库 final、筛选后隐藏且编辑器保留、`aria-pressed` 正确、切回草稿、批量/AI/历史版本按钮仍在、0 控制台错误 |
| F28 `run_command` 路径校验误伤内联脚本：`validateRunCommandArgs` 对含 `..`/以 `/` 开头的参数一律拒绝，而 JS 展开 `...prev`、URL 字符串属于正常代码，错误文案只有「arg is outside the workspace」，子代理误以为要换别的写法并反复尝试 | 错误文案追加「若这是内联脚本里的字符串/URL，请改用 edit_file 修改文件，不要用 run_command 打补丁」；子代理提示新增第 12 条：改源码只用 edit_file/write_file、禁用内联脚本打补丁、被拒后不重试同类命令、预算优先花在写入上；契约测试新增 `...` 展开用例，prompt 单测 2 条断言 |
| F29 遗留失败契约测试：F21 把 `read_file` 硬上限提到 4MiB 后，`workspace-tools.contract.test.ts` 仍断言「64KiB 就拒绝读取」，测试一直红着 | 读上限用例改为 4MiB+1 并断言新文案；`workspace-tools` 契约 48 passed、prompt 2 passed，合计 50 passed；全仓 typecheck 通过 |

#### 本轮观察

- 首轮子代理把 20 次工具额度耗在读取 2782 行页面与后端改动上，前端未落地，但**如实汇报了「部分完成」**（F2/F19 生效，没有谎报）；补发一轮「只做三处 edit_file」后一次通过。大文件多改动任务需要「先写后验、预算给写入」的显式提示，已写进 F28。
- 子代理把「内联脚本打补丁」当作批量修改的捷径，而该捷径被路径校验拒绝且提示不可执行——错误文案决定模型下一步，这类「拒绝但不可行动」的错误应统一补齐下一步指引。

### 6.18 第十五轮：定稿进度（批次 Q）

| 内容 | 验证 |
|------|------|
| 后端：`listBooks()` 改 `LEFT JOIN chapters` 聚合 `chapterCount` / `doneChapterCount`（`COALESCE` 兜底，原字段经 `mapRow` 全部保留）；`GET /api/books/[id]/stats` 增加 `doneChapterCount` | 新增 `tests/book-progress.test.mjs` 2 条：两本书各 2/1 章时分组不串行、1 章定稿 → 2/1；空书 0/0；既有 title/genre/createdAt/updatedAt 仍在。`pnpm test` **17/17** |
| 前端：书架书卡显示「定稿 x / y 章」+ 细进度条（y=0 不除零、宽度封顶 100%）；`/stats` 作品对比 meta 补「定稿 x / y」 | `pnpm typecheck` 通过；clean `pnpm build` exit 0；重启 3210 后 Playwright **12/12**：API 聚合字段存在且与 stats 一致、书架 0/1、把章节设为 final 后 1/1 且条宽 100%、`/stats` 两行分别 1/1 与 0/1、恢复 draft 后回落 0/1、演示数据已复原、既有入口与按钮仍在、0 控制台错误 |

#### 本轮观察

- 本轮未暴露新的闭环缺陷：单子任务一次完成后端+前端+测试，`startedTasks=1`，并用 `edit_file` 增量改 4 个文件；F28 的新提示（禁内联脚本、预算优先写入）在这次任务里没有被触发。
- 聚合字段走 SQL 后，`mapRow` 对未知别名原样透传的行为需要测试兜住（本轮断言了既有字段未丢），这是 JS 仓库里最容易静默回归的点。

### 6.19 第十六轮：单章导出（批次 R）

| 内容 | 验证 |
|------|------|
| `src/lib/chapter-export.js` 纯函数 `buildChapterExport(chapter, format)`：md 首行 `# 第 N 章 标题`、txt 首行 `第 N 章 标题`、正文前空一行；format 仅认 `txt`，其余按 md（与整书导出同口径）；空标题「未命名」、空正文只留标题；filename 经 `encodeURIComponent` | `tests/chapter-export.test.mjs` 6 条，`pnpm test` **23/23**；`pnpm typecheck` 通过 |
| 路由 `GET /api/chapters/[id]/export?format=md|txt`：id 非法 400、章节不存在 404、`Content-Disposition: attachment; filename*=UTF-8''…`；编辑区工具条加「导出本章 MD」链接（`download`） | clean `pnpm build` exit 0；curl：md 返回 `text/markdown` + `attachment; filename*=UTF-8''第 1 章 红笔.md`、首行 `# 第 1 章 红笔`，txt 首行 `第 1 章 红笔`，`abc` → 400、`99999` → 404；Playwright 6/6：链接存在、href 正确、点击下载文件名 `第 1 章 红笔.md`、既有按钮仍在、0 控制台错误 |

#### 本轮观察

- 子代理本轮两次 `pnpm build` 都接近 120s 上限（一次超时无输出被额度打断，一次成功），本机 clean build 实测约 50–60s，说明子代理侧的超时余量偏紧；F16 的 120s 对 `next build` 仍可能不够，后续可考虑按项目类型给 180s。
- 除构建耗时外无新缺陷：单子任务完成、`startedTasks=2`（实现+补充），未触发路径校验与额度问题。

### 6.20 第十七轮：阅读模式（批次 S）+ F30

| 内容 | 验证 |
|------|------|
| LingWen 阅读模式：编辑区「阅读模式」按钮 → fixed 全屏只读覆盖层（`第 N 章 标题` + 上一章/下一章/关闭），正文取 `editContent`（含未保存改动），按 `chapters` 原始顺序切章并同步选中章节，首/末章禁用，Esc 关闭；`≤600px` 顶部按钮换行 | `pnpm typecheck` 通过；clean build 产物完整（路由表含 `/books/[id]` 12.6 kB，进程退出仍挂起触发 exit 124，属已知现象）；Playwright **17/17**（临时书 + 2 章）：覆盖层、标题/正文、首末章禁用、切章、Esc、关闭按钮、临时书已删除且 404 |
| 补一轮修复：首版上一章/下一章直接 `setSelectedId`，绕过 `handleSelectChapter` 的未保存确认，切章会静默丢草稿 | `handleSelectChapter` 改为返回 boolean 并复用；Playwright 实测「输入后立即点下一章」弹出「有未保存修改，切换将丢失，继续？」，取消仍停在第 1 章，确认后切到第 2 章 |
| F30 构建超时余量：`LONG_RUNNING_COMMAND_TIMEOUT_MS` 120s → 180s（本机 clean build 需 100–120s，120s 无余量，子代理多次被中途杀掉） | `tool-boundary.test.ts` 断言同步为 180s，9 passed；全仓 typecheck 通过；4522 已重启加载 |

#### 本轮观察

- 子代理新建交互时没有复用仓库里已有的「切换章节前确认」保护，首版实现能通过它自己的 typecheck/build 却会丢数据——纯构建门禁抓不到交互语义回归，必须靠浏览器端行为断言（本轮用临时书验证后删除）。
- 推送期间 mihomo 代理多次抖动（`Connection timed out during banner exchange`），WFXM 重试后成功，LingWen 连续失败；这是环境问题，不影响本地提交。

### 6.21 第十八轮：工作台全局命令面板（批次 T）

| 内容 | 验证 |
|------|------|
| LingWen 工作台新增「命令」按钮 + `Cmd/Ctrl+K` 命令面板：浮层 + 遮罩、Esc/点遮罩关闭、搜索框自动聚焦、按名称/关键词过滤、↑↓ 移动高亮、Enter 执行、hover 改选中、无匹配「未找到命令」、无选中章节时依赖章节的命令置灰；12 条命令全部复用现有处理函数（不新增后端） | `pnpm typecheck` 通过；clean build 产物完整（29 条路由，exit 124 属已知）；Playwright **15/15**：按钮/快捷键开关、聚焦、12 条命令、过滤、空态、↑↓/↑ 往返、Enter 执行「书籍设置」、Esc、点遮罩、章节选中后既有按钮与导出链接仍在、390px 无横向溢出、零 JS 异常 |
| 交互缺陷（子代理首版）：↑↓ 高亮不动，始终停在第一条 | 根因：`paletteCommands` 的 `useMemo` 依赖里有未 memo 化的普通函数（`handleCreateChapter`/`handleOpenReader`/`handleReview`/`handleStartPolish`/`openBookSettings`/`cancelBookSettings`），每次渲染重算 → `paletteFiltered` 每次都是新数组 → 「重置选中项」effect（依赖 `[paletteOpen, paletteFiltered]`）每次渲染都把 `paletteIndex` 打回第一个可执行项。修复：处理函数收进 `paletteHandlersRef`、useMemo 依赖收敛到真正影响内容的稳定值；重置 effect 依赖改为 `[paletteOpen, paletteQuery]`。复测 ↑↓ 与 ↑ 往返通过 |
| 数据与回归 | 演示库 book2 仍 1 章（id=3，353 字，draft）、无新增版本/会话；专注模式仅写 localStorage；既有 Cmd/Ctrl+S 保存、阅读模式 Esc、章节点击载入 423 字正文均正常 |

#### 本轮观察

- 子代理写出的 React 代码能过 typecheck/build，但 effect 依赖写错导致键盘交互静默失效——这类问题只能由浏览器行为断言发现，再次印证「构建门禁 ≠ 交互正确」。
- 本轮为纯前端增量，只读 + Playwright 即可闭环；子代理两轮（实现 + 修复）分别耗时约 90s 与 50s。

### 6.22 第十九轮：书架排序 + 最近编辑时间（批次 U）

| 内容 | 验证 |
|------|------|
| 后端 `listBooks({ sort })` 支持 `updated`（默认）/`created`/`title`/`words` 四种白名单排序，新增聚合列 `wordCount`（SUM word_count）与 `lastEditedAt`（章节 updated_at 最大值，无章节回落 books.updated_at）；`GET /api/books?sort=` 非法值 400 | `tests/book-sort.test.mjs` 3 条（四书四序、0 章节回落与 JOIN 不放大、同值 id 兜底）；`pnpm test` **26/26**；typecheck 通过；curl 实测四种排序顺序正确、`?sort=bad` 返回 400 与明确 error |
| 书架页新增排序下拉（最近编辑/最近创建/书名/字数），切换后按 `?sort=` 重新拉取，选择存 localStorage `lingwen.shelf.sort`；书卡新增「最近编辑 MM-DD HH:mm」与「N 篇 · M 字」（千分位），定稿进度保留 | clean build 产物完整（exit 124 属已知）；Playwright **12/12**：默认最近编辑（导入书在前）、四选项、时间/字数文案、切换书名后首卡变为《长夜将至》、字数/创建时间排序、刷新后沿用书名排序、书架搜索仍可用、390px 无横向滚动、零 JS 异常 |
| 数据与回归 | 演示库仍 2 本书各 1 章（353/350 字），全程只读；搜索、导入导出、进入工作台等既有入口未受影响 |

#### 本轮观察

- 父代理在首轮决策时命中 `E-LLM-01`，但 toolCalls=1 已派发子代理，失败信封正确提示「任务已交给后台执行、不要原样重发」，实际子代理正常完成——F9/F17 的信封在真实故障下生效，未造成重复派发。
- 仅 2 本演示书不足以在 UI 层区分「字数/创建时间」与「最近编辑」的排序差异（顺序恰好相同），这两种排序的严格性由 `:memory:` 单测覆盖，UI 只验证「切换后确实重新请求且列表按返回顺序渲染」。

### 6.23 第二十轮：全书查找替换（批次 V，口语折中需求）+ 新缺陷

| 内容 | 验证 |
|------|------|
| 需求口吻改为「正文像真人说话 + 末尾 3 条验收点」后，LingWen 新增全书查找替换：`src/lib/find-replace.js`（纯函数 `countOccurrences`/`applyReplacement`/`buildSnippets`、只读 `previewBookReplace`、事务版 `replaceBookText`）、`POST /api/books/[id]/find-replace`（mode=preview/replace + confirm:true）、`/books/[id]/find-replace` 面板页 + 工作台入口、`tests/find-replace.test.mjs` | `pnpm test` **31/31**；typecheck 通过；clean build exit 0（`ƒ /api/books/[id]/find-replace`、`ƒ /books/[id]/find-replace`）。API 13 项：预览 2 处/1 章+片段、缺 confirm 400、替换后正文「刀芒如虹。刀芒再起。无关内容。」、wordCount=12、未命中章不变、旧词 0 命中、1 条历史快照、临时书删除后 404 |
| UI（Playwright **12/12**） | 工作台入口可进面板、预览汇总与 `<mark>` 高亮、确认前正文不变、二次确认文案含「2 处 / 1 章」、取消不替换、确认后提示「共替换 2 处，涉及 1 章」并刷新为 0 命中、返回书籍、390px 无横向滚动、零 JS 异常；临时书已删除 |
| 数据 | 演示库仍 2 本书各 1 章（353/350 字）；替换测试全在临时书内完成 |

#### 本轮暴露的 WFXM 问题（待修）

| 候选编号 | 现象 | 证据 | 定级 |
|---|---|---|---|
| F31 | 同一会话里**已完成的任务被重新派发**：本轮父代理把上一轮的「书架排序」与新需求一起当成「两个任务」并发派给子代理，重复子代理又改了 `src/app/page.tsx`（加 `book-meta` 类）与 `globals.css`；实际功能上一轮已交付 | `/demo/api/status` 的 `startedTasks` 由 3 → 4 → 5（两次派发）；子代理 1 的回复整段复述已完成的 `listBooks` 排序；`page.tsx` 仅 +1/-1 类名、CSS +227 行含重复语义样式 | P1 |
| F32 | 子代理工具预算耗尽时**功能已落地但测试仍红**（1 条断言），worker 直接收工，父代理不自动续跑，只能 owner 再发一轮「只修这条断言」 | 子代理 2 报告「测试：✗」「工具预算耗尽，剩 1 行测试断言待修」；补发一轮后才 31/31 | P1 |
| F33 | 需求写「在工作台加个面板」，子代理实现为独立的 `/books/[id]/find-replace` 页面 + 工具栏链接（可用但偏离「工作台内面板」） | `src/app/books/[id]/find-replace/page.tsx` 新建整页；工作台仅加一个 `<Link>` | P2 |

> 状态：F31/F32 已修（见 §6.24）；F33 仍为观察项（功能可用，仅位置偏离原意）。

#### 本轮观察

- 口语化需求下子代理仍完成了跨 6 个文件的实现（2 个新 API/页面 + 1 个 lib + 测试 + 两处页面接入），但**验收偏差**与**收尾不完整**明显增加：多派发一次旧任务、测试红着收工、面板位置自选。
- 测试断言错误是子代理自己写错的期望值（删除词后句号相邻），实现语义正确；这类「自测红但不修」暴露的是 worker 完成判定只看「是否有回复」而不看「门禁是否全绿」。

### 6.24 F31/F32 修复（WFXM 侧）

| 编号 | 修复 | 验证 |
|------|------|------|
| F31 | 新增 `apps/api/src/delegation-dedupe.ts`：派发前读取审计日志**尾部**（`readRecentSubagentAuditTail(200, env)`，最多 512KiB，避免 11MB 全量读），筛出同一 `parentConversationId` 下已有 `completion` 的 `delegation`，与本次 task 做相似度比较；≥ 阈值则拒绝派发并返回「已阻止重复派发…如确需返工请写明修改点」；`BUTLER_V5_DELEGATION_DEDUPE=0` 可关闭，`BUTLER_V5_DELEGATION_DEDUPE_THRESHOLD` 可调（默认 0.45，区间 0.3–0.95）；含「返工/修复/重做/…」字样的任务直接放行 | 单测 `delegation-dedupe.test.ts` **9 条**（归一化、token+bigram 相似度、同会话已完成拦截、未完成/跨会话/超 24h/过短不拦截、返工放行、开关与阈值、拒绝文案）；**用真实审计日志回放**：上一轮 `067476f6eae9` 与重复派发 `3b053eb2d792` 的任务相似度 **62.6%**（旧 Levenshtein 仅 74.2%，低于任何安全阈值，故改为 token/bigram 组合），现可拦截；新任务/跨会话/返工均放行 |
| F32 | `dev-quality-gate.ts` 新增 `enrichSubagentDevReplyWithVerify`（返回原始 verify 结果）、`shouldAutofixDevFailure`（纯函数判定）、`buildDevVerifyFixTask`（把失败命令+输出摘录拼成续跑任务）、`isDevVerifyAutofixEnabled`；`subagent-worker.ts` 在门禁红灯且有写/命令能力时自动续跑**一轮**（新预算），复检仍红则把子任务标记为失败，不再以「已完成」交付；`BUTLER_V5_DEV_VERIFY_AUTOFIX=0` 可关闭 | 单测：`shouldAutofixDevFailure` 6 组分支 + `buildDevVerifyFixTask` 2 条；端到端（4523 临时实例 + `BUTLER_V5_DEV_VERIFY_CMD='["false"]'` + 空工作区）：子代理写 `hello.txt` 后日志出现 `dev gate red (exit=1); starting one auto-fix round`，续跑回复送达，最终回复仍显示 `测试：✗`（门禁恒失败），临时工作区已删除 |
| 回归 | `delegation-dedupe.test.ts` 9 + `dev-quality-gate.test.ts` 新增 4 + `tools/subagent-worker/audit-log` 相关共 **87 passed**；全仓 `typecheck` 通过；4522 已重启加载最终代码；演示库与 LingWen 工作区未受影响 | 见上 |

#### 设计取舍

- 相似度改用 `max(token Jaccard, 字符二元组 Jaccard)`：真实复现的两个任务被改写后字符级距离很大，但功能关键词（「书架排序 + 最近编辑时间」/`listBooks`/`tests/book-sort.test.mjs`）高度重合；实测重复对 0.48/0.58，而非重复任务最高仅 0.25/0.35，阈值 0.45 有安全边界。
- 只读审计尾部：审计日志含每个工具调用，已达 11MB；守卫不能每次派发全量读盘。
- F32 自动续跑只做一轮且仅在「有写/命令能力 + 非审批暂停 + 门禁启用」时触发，避免无限循环与费用失控。

## 7. 边界

- 未实现多用户/鉴权、版本历史、批量生成、人物关系图谱。
- 不提交、不推送：等待 owner 明确指令。
- 生产 `WFXM/.env`、butler-v5 既有配置不改；LingWen 的 key 仅存 `.env.local`（已忽略）。
