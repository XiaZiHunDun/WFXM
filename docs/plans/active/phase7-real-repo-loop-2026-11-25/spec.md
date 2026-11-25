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

### 6.3 收口验证（真实 LLM 烟测 + UI）

- 构建：`pnpm build` 通过，路由表含 `/`、`/books/[id]`、10 个 `ƒ /api/*`。
- 服务：`next start -p 3210`（LLM 用 DeepSeek OpenAI 兼容端点，仅进程环境变量，未写入仓库）。
- API 烟测：建书 → 加设定 → LLM 生成 3 章大纲 → 建章节 → `generate` 流式返回 1165 字节 → 落库 `wordCount=334`、`status=drafted` → `check` 返回 stats/issues → `export?format=md` 带 `Content-Disposition`。
- UI（Playwright + 本机 headless Chromium）：书架 1 本《长夜将至》；工作台 3 栏、3 条大纲、1 章、1 条设定；点击章节后编辑器载入 399 字正文；体检面板返回「大纲覆盖率偏低」。
- 内置浏览器桥接（Agent 与 Skill 两条路径）访问 `127.0.0.1:3210` 均超时，改用本机 Chromium 完成验证；该环境问题已记录为验证通道限制。

## 7. 边界

- 未实现多用户/鉴权、版本历史、批量生成、人物关系图谱。
- 不提交、不推送：等待 owner 明确指令。
- 生产 `WFXM/.env`、butler-v5 既有配置不改；LingWen 的 key 仅存 `.env.local`（已忽略）。
