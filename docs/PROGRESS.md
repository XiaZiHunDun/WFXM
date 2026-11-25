# 开发进度台账（阶段记录）

> **用途**：按「阶段」记录开发进度——目标、验收口径、证据、遗留。D-series 单笔 ship 仍记 [`ROADMAP.md`](ROADMAP.md)；架构依据见 [`DESIGN.md`](../DESIGN.md) 与 [`architecture/wfxm-agent-runtime.html`](architecture/wfxm-agent-runtime.html)。
> **新会话**：先读 [`HANDOFF.md`](HANDOFF.md) 恢复当前运行态与待办，再读本台账。
> **更新时机**：阶段开始/结束时；验收证据必须是复跑结果，不引用历史结论。
> **最近更新**：2026-11-23

---

## 阶段总览

| 阶段 | 目标 | 状态 | 验收日期 |
|------|------|------|----------|
| Phase 1 | 主要流程打通，基础功能正常，不报错，无明显消息丢失 | ✅ 完成 | 2026-11-19 |
| Phase 2 | 功能深化（爆点/差异化），按 ROI 选点 | ✅ 完成（测评体系 + C1 提醒 / C2 审批预览 / C3 周报） | 2026-11-23 |
| Phase 3 | 功能打磨：地基 → 楼层 → 体验 | ✅ 完成（任务层 / 管家层 / 渠道与产品能力） | 2026-11-23 |
| Phase 4 | 验证实际开发能力：用 WFXM 开发实际可用项目 | ✅ 完成（Ledger Lite 记账应用） | 2026-11-23 |

---

## Phase 1 — 主流程打通（✅ 2026-11-19）

### 目标与验收口径

链路：微信入站 → 管家层（规则引擎 + ButlerRuntime）→ 任务层（pi 原生 Agent）→ 微信出站。
达标定义（四条同时满足）：

1. 主流程打通（帮助、工具执行、写文件、多轮记忆、长回复都能走通）；
2. 基础功能正常（渠道、记忆、审批、沙箱、MCP 可用）；
3. 不报错（无 5xx、无内部降级话术、无异常泄漏到用户侧）；
4. 无明显消息丢失（重投、并发、连续投递均不丢不重）。

### 验收证据（2026-11-19 复跑）

| 项 | 结果 |
|----|------|
| `pnpm typecheck` / `pnpm lint` / `pnpm format:check` | 全绿，0 warning |
| `pnpm test` | 312 文件 / 2252 通过 / 2 skipped |
| L4 主流程（`npx tsx scripts/l4-smoke.ts`） | 5/5 |
| L4 可靠性（`--suite reliability`） | 5/5（重投回放、同会话并发、跨会话并发、无待审批、连续三条） |
| 网关服务 | `butler-v5-gateway.service` active，health=200，冷启动 <10s，MCP 4 个 server 全部引导完成 |
| 真机渠道 | iLink 入站鉴权修复后，微信端收发正常；失败推送真机确认收到 |

### 本阶段闭环的问题

| 问题 | 结果 |
|------|------|
| iLink 入站缺 `x-inbound-secret`，401 静默丢弃 | 补齐鉴权与日志，消息不再丢 |
| 三个旁路未走消息出口，markdown/内部术语泄漏 | 统一 `finalizeReply`，术语表 + L3 断言 |
| 「记住」不落库、召回靠整句匹配 | 自然语言标记确定性写入 + 中文 bigram 召回 |
| plan 模式剔掉写入工具后无列目录能力 | 新增 `list_dir`；后补进 `WECHAT_CORE_TOOL_NAMES` 白名单 |
| 审批文案重复泄漏原始 MCP 工具名 | 按 provider 生成中文服务名 |
| 只读任务 40–60s、冷启动 123s | plan 模型切 `deepseek-v4-flash`；修复沙箱 HOME/挂载与逐 server 引导超时 |
| 沙箱内 `python3` 找不到 stdlib | `resolveSandboxVisiblePath` 过滤宿主 PATH |
| 重投二次执行、兜底回复不落库 | 按 `messageId` 回放已存回复；兜底路径补 `persistAssistantReply` |
| 子代理假成功 | capped 判定改为失败并推送「执行未完成」 |

### 仓库整理（同阶段收尾）

- 删除已退役的 v4 Python 主线（代码、测试、脚本、语料、schema、数据）与 218 篇 v4 文档；
- 删除 `_archive/` 脚手架、一次性 spike/smoke 脚本、过期审计 dump；
- `butler-v5/` 扁平化为仓库根：`apps/ packages/ cli/ vendor/ tests/ scripts/ config/` 上移，CI/部署/依赖路径同步；
- 修复 Docker 构建上下文（Dockerfile 曾与 COPY 路径不匹配）、补 `vendor/pi-agent` 入库（此前被忽略导致干净 clone 无法构建）。

### 遗留与风险（不阻塞 Phase 2）

| 项 | 说明 |
|----|------|
| capped 分支 | 模型未跑满 12 轮，真机只验证了推送通道，判定本身仍靠单测 |
| compose 启动告警 | `POSTGRES_PASSWORD missing`，容器已在运行故不影响，但首次全新部署需补齐 |
| 本机 SSH 代理 | `127.0.0.1:7890` 不可用时 push 需 `ProxyCommand=none` |

### 遗留补齐（2026-11-23）

| 项 | 结果 |
|----|------|
| 审批超时过期 | `PiTaskRunner.approvalTtlMs` 经 `BUTLER_V5_APPROVAL_TTL_MS` 可配置（默认 30 分钟，`<=0` 关闭）；过期后清空 pending、写入 `lastReply`，管家卡片与规则路径均回「审批已过期，本步未执行。」，不再误报「已确认」；legacy `approveWaitingStep` 过期时同样给出明确文案 |
| 乱序到达 | 新增 `apps/api/src/inbound-ordering.ts`：会话级序号（Slack `ts`、Telegram `message_id`）+ 时间窗（`BUTLER_V5_INBOUND_ORDER_WINDOW_MS`，默认 120s，`0` 关闭）；旧消息不追加事件、不执行、不发送，响应带 `skipped/skipReason`，trace 为 `inbound-order:<reason>`；iLink 提供 `create_time/msg_time` 时同样生效 |
| 边界 | 排序状态为进程内、有上限；多进程或跨重启不共享，无排序元数据的渠道退化为按到达顺序 + 既有幂等去重 |

验收证据（2026-11-23 复跑）：

| 项 | 结果 |
|----|------|
| `pnpm test` | 279 文件 / 2,423 通过 / 2 skipped |
| `pnpm typecheck` / `pnpm lint` / `pnpm format:check` | 全绿，0 warning |
| `pnpm verify:butler` | 3 场景 / 13 轮全过 |

---

## Phase 2 — 功能深化（✅ 2026-11-23）

> 本阶段包含两块：**测试与评估体系**（✅ 已收尾）与**功能深化（爆点/差异化）**（✅ 已收尾，C1–C3 已交付）。首块任务书见 [`plans/active/phase2-test-eval-system-2026-11-19.md`](plans/active/phase2-test-eval-system-2026-11-19.md)。
>
> 注意：部分测评文档（如 [`phase3-eval-system-2026-11-19.md`](plans/active/phase3-eval-system-2026-11-19.md)）里的 “Phase 2 / Phase 3” 指测评设计内部阶段，不是项目阶段编号。

### 测试与评估体系（✅ 已收尾，2026-11-20）

| 层 | 交付 | 证据 |
|----|------|------|
| L0 结构不变量 | 24 个 `section*` 守卫 → 8 个不变量文件 | `pnpm vitest run tests/architecture` |
| L1 契约 | `tests/contracts/{tools,messages,state}` 8 个文件，共 221 用例 | `pnpm vitest run tests/contracts` |
| L2 集成 | `tests/integration` 12 条 outcome-only 场景 | `pnpm vitest run tests/integration` |
| L3 轨迹 | `tests/trajectories` 18 条 JSON | `node src/cli.mjs run --suite trajectory --runtime wfxm` → 18/18 |
| L4 开放任务 | agent-eval `tasks/butler-open` 20 条 + 真实 judge（双评、温度 0） | nightly `--judge-observe`；稳定两周后转 `--judge` |
| 真实模型基线 | capability / heldout(11) / repo(5) + RAG 多指标 gate | nightly 与 release 均按基线门禁 |
| CI | PR 跑单测与审计；nightly 跑 L3–L4 + 真实模型；release 复用 eval-gate | `.github/workflows/{ci,nightly,release}.yml` |

全量回归：`pnpm test` → 276 文件 / 2,285 通过 / 2 skipped；`pnpm typecheck`、`pnpm lint`、`pnpm format:check` 均通过。
清理幅度：测试文件 314 → 273（`git ls-files '*.test.ts'`），用例 2,346 → 2,285；两轮清理见 findings §8。
评估体系：Phase 3 P0–P3 与 A–D 增强已完成——防作弊（hiddenChecks / tamperPolicy / honestStop / quality）、
过程指标、配对 lift、变异抽查、模型矩阵、读写 p95 拆分与真实 judge 均已接入；
14 条旧场景迁入 legacy 套件，5 条依赖内部 trace 的场景保留在 vitest。
2026-11-20 复跑 11 条 heldout 矩阵：DeepSeek 11/11（P95 26s）对 MiniMax 8/11（P95 71s），默认模型维持 `deepseek-flash`。
发现的问题记录在 [`plans/active/phase2-findings-2026-11-19.md`](plans/active/phase2-findings-2026-11-19.md)（F-01…F-12），其中 F-02「终态 Run 被同幂等键重投后复活」与 F-12「审批提示暴露原始工具名」已修复并补回归用例。

入口条件：

1. Phase 1 验收证据保持最新（任一回归先修复）；
2. 从 [`ROADMAP.md`](ROADMAP.md) §4（维度 2）与 [`plans/active/v5-post-boundary-roadmap-2026-08.md`](plans/active/v5-post-boundary-roadmap-2026-08.md) 选定 2–3 个 owner 撞点；
3. 每个选点写明：用户场景、成功判据、失败可见性、回滚方式。

### 功能深化（✅ 已收尾，2026-11-23）

选点：按入口条件从 [`plans/active/phase2-feature-deepening-2026-11-23.md`](plans/active/phase2-feature-deepening-2026-11-23.md)
的候选中选定 C1 + C2 + C3；C4（入站图片 / 文件理解）明确不做。

| 选点 | 用户场景 | 交付 | 规格 |
|------|----------|------|------|
| C1 自然语言提醒 | 微信一句话创建一次性 / 每天 / 每周提醒，到点主动推送，可查看 / 取消，重启不丢 | `reminders` 表 + 3 个工具 + reminder worker | [spec](plans/active/phase2-c1-reminders/spec.md) |
| C2 审批前预览 | 审批消息直接展示 `write_file` diff / `run_command` 全文，降低误批 | 纯渲染器 + 审批链路 + owner `preview` 字段 | [spec](plans/active/phase2-c2-approval-preview/spec.md) |
| C3 每周周报 | 每周固定时间推送完成 / 待办 / 失败 / 审批四项数字，也可 `/周报` 手动查看 | weekly-digest 统计/渲染 + 手动命令 + 定时 worker | [spec](plans/active/phase2-c3-weekly-digest/spec.md) |

验收证据（2026-11-23 复跑）：

| 项 | 结果 |
|----|------|
| `pnpm test` | 288 文件 / 2,480 通过 / 2 skipped |
| `pnpm typecheck` / `pnpm lint` / `pnpm format:check` | 全绿，0 warning |
| 冒烟 | 提醒：本地端到端 + 真实 iLink 推送成功；周报：acceptance 覆盖手动与自动推送 |
| 默认开关 | C1 / C2 / C3 均默认关闭；关闭后无工具注册、worker 启动或文案变化 |

本阶段闭环的问题：

| 问题 | 结果 |
|------|------|
| 提醒时间歧义 / 非法日期 | 统一 `Asia/Shanghai`；非法日期与过去时间返回可读原因，不猜测 |
| 审批正文只有「需要修改文件 X」 | 审批消息与 owner API 增加 diff / 命令全文，超限截断并标注 |
| 周报数字口径不统一 | 复用 TaskStore / tracer `run_failed` / `approval.requested` audit，与 `/tasks`、`/usage` 对齐 |

遗留（不阻塞 Phase 2 关闭）：

| 项 | 说明 |
|----|------|
| C4 入站图片 / 文件理解 | 需 OCR / 多模态能力，当前无 owner 痛点实证，暂不做 |
| 公网 Demo / 自托管手册 | 属 ROADMAP §4 后续维度，不在本阶段范围 |
| 提醒 / 周报默认关闭 | 生产需显式开启并配置接收人；后续按 owner 手试反馈再评估默认值 |

> 阶段收尾已按约定完成（2026-11-23），总览表状态已改为 ✅。

---

## Phase 3 — 功能打磨（✅ 2026-11-23；任务层地基 ✅ 2026-11-20、管家层 ✅ 2026-11-23、渠道与产品能力 ✅ 2026-11-23）

> 任务层 B1–B10、管家层 B11–B16、渠道与产品能力 C1–C6 均已交付。C3 保持旧入口为生产默认，但已补齐 per-channel 灰度开关与回退；遗留项见阶段收尾与「遗留清理」。

### 目标与验收口径

以任务层为地基，按「任务契约 → 转录 → 工作区 → 工具协议 → 审批 → 持久化 → 调度 → 模型上下文 → 结果契约 → 端到端可见性」十层逐层打磨。
每层同步补关键点测评：只锚定外部可观察契约与安全边界，不断言内部实现细节。

### 任务层验收证据（2026-11-20 复跑）

| 项 | 结果 |
|----|------|
| `pnpm test` | 277 文件 / 2,340 通过 / 2 skipped |
| `pnpm typecheck` / `pnpm lint` / `pnpm format:check` | 全绿，0 warning |
| 内部分诊审计 | 49 条 internal-only（2.4%，未超预算） |
| 批次关键点用例 | 43 条，覆盖 runner / native tools / adapter / butler |

### 本阶段闭环的问题

| 问题 | 结果 |
|------|------|
| 同任务并发竞态 | `queued` 守卫前置，第二个 turn 直接拒绝 |
| 额度耗尽/批次阻断时空回复 | 回复优先级改为待审批 → 失败 → 暂停 → 终止原因 → 模型文本 |
| snapshot 损坏静默进入执行 | 校验版本/结构/首条 system/toolResult，显式失败 |
| 工作区路径边界无直接测试 | 15 条边界用例；悬空符号链接 fail-closed |
| 审批跨进程重复执行 | `decidedAt` 声明 + TTL，跨 runner 恰好一次 |
| close 后被最后一笔 save 复活 | `closed` 标记，关闭中的 turn 不写回 |
| 超时被误报为 idle | 超时映射为 `failed` 并保留具体原因 |
| 任务结果不回流管家层 | `lastReply` / `lastError` 持久化并在 `/new`、`/status`、审批回调中展示 |
| 任务结果泄漏 workspace 绝对路径 | adapter 统一脱敏为“项目目录” |

### 管家层打磨（✅，2026-11-20 起）

| 批次 | 内容 | 状态 |
|------|------|------|
| B11 | 审批授权与归属：任务绑定会话、跨会话拒绝、区分已处理/无权/不存在 | ✅ |
| B12 | 任务编排与 activeTaskId：裸确认按会话推导待审批任务；任务列表与单查支持重启后恢复；项目过滤 | ✅ |
| B13 | 规则路径韧性：任务层/存储故障给可读回复，消息不丢 | ✅ |
| B14 | 记忆单一事实源：召回按用户隔离，自动记忆投影触发点，写入失败隔离 | ✅ |
| B15 | 路由可用性：`/status <任务ID>` 支持显式查询，未知 ID 指向 `/tasks`，帮助文案同步 | ✅ |
| B16 | 体验收口：审批通知与最终出口统一脱敏，绝对路径归为“项目目录”，长回复分段回归 | ✅ |

### 渠道层与产品能力打磨（✅，2026-11-23 起）

> 方案：[`plans/active/phase3c-channel-product-2026-11-23.md`](plans/active/phase3c-channel-product-2026-11-23.md)

| 批次 | 内容 | 状态 |
|------|------|------|
| C1 | 出站一致性与分段：Slack/Telegram 统一收口并按渠道分条，部分失败可感知 | ✅ |
| C2 | 入站重复投递：无 messageId 时按内容 + 时间窗生成幂等键 | ✅ |
| C3 | 渠道-管家边界：暂不切换，能力矩阵与切换前置条件写入方案 §6 | ✅ |
| C4 | 任务主动通知：detached 任务暂停/完成经 ChannelPort 推送 | ✅ |
| C5 | 显式记忆：`/remember`、`记住：X` 落库并回执 | ✅ |
| C6 | 项目切换：`/project` 写入会话并跨重启保留 | ✅ |

### 阶段收尾（2026-11-23）

收尾清理：

- 文档：删除已完成 stub（`v5-remaining-work-2026-08-20.md`）与已关闭的 issue 草稿（`v5-p3-mcp-contract-issue-draft-2026-08.md`），同步 README / plans 索引与 knowledge manifest；更新 `TESTS.md`、`API_ENDPOINTS.md`、`FEATURES.md`。
- 代码：删除未接线的 `notifyApprovalIfPaused` 及其重复测试；移除未使用的 `@effect/schema` 依赖。`knip` 剩余项为 re-export 误报（`undoChain_listChainIds`、`ChainEntry`、`ChainRevertResult`），有真实调用，保留。

验收证据（2026-11-23 复跑）：

| 项 | 结果 |
|----|------|
| `pnpm test` | 277 文件 / 2,379 通过 / 2 skipped |
| `pnpm typecheck` / `pnpm lint` | 全绿，0 warning |
| 内部断言审计 | 49 条 internal-only（2.4%，2,082 用例） |

阶段结论：任务层、管家层、渠道层与产品能力打磨完成；C3 按决策保持旧入口为生产默认，未做默认 cutover。

### 遗留清理（2026-11-23，同日）

| 项 | 结果 |
|----|------|
| 管家能力面 | 补齐 `/retry [任务ID]`、`/diagnose`、`/undo` 边界；`/diagnose` 不调模型，`/undo` 只给手工回滚指引 |
| 任务层重试 | `ButlerTaskPort.retry` + pi 适配器：failed/idle/closed 重跑，paused 有 pending 时不自动批准 |
| 渠道 cutover | per-channel `BUTLER_V5_<CHANNEL>_ENGINE`（优先）/ 共享 `BUTLER_V5_CHANNEL_ENGINE`，默认 legacy；`BUTLER_V5_CHANNEL_PROJECTS` / `BUTLER_V5_DEFAULT_PROJECT_ID` 决定管家项目 |
| 契约测试 | 覆盖 butler/legacy 路由分支、provider 缺失与 assembly 失败 503、引擎与项目解析、任务端口重试 |

验收证据（2026-11-23 复跑）：

| 项 | 结果 |
|----|------|
| `pnpm test` | 278 文件 / 2,405 通过 / 2 skipped（含第二批收尾） |
| `pnpm typecheck` / `pnpm lint` / `pnpm format:check` | 全绿，0 warning |
| `pnpm verify:butler` | 3 场景 / 13 轮全过（含 `/diagnose` `/undo` `/retry`） |

### Phase 3 收尾（2026-11-23，第二批）

| 项 | 结果 |
|----|------|
| 质量门 | 抽出 `runQualityGate`，旧 `/验` `/门禁` 与管家 `/门禁 [步骤]` 共用同一实现；未注入时给可读提示 |
| 子代理 | 新增 `ButlerSubagentPort` 与 `delegate_to_subagent` 工具，由 `BUTLER_V5_SUBAGENT_ENABLED` 控制，包装既有 delegate 工具 |
| ChannelPort 契约 | 空文本统一 `EMPTY_CHANNEL_TEXT_REASON`；wechat / slack / telegram 出站口一致；generic 走 no-op 并在响应体回传 |

遗留与风险（不阻塞，需单独立项）：

| 项 | 说明 |
|----|------|
| 进程内并行 | 全局锁为 FIFO 串行；真正的并行需多 worker / 多进程设计 |
| 429/5xx 重试 | 委托 `retryAssistantCall`，未新增网络级重试用例 |
| judge 严格模式 | 仍为 observe，稳定后再转 `--judge` |

补充验证（2026-11-23）：

- 基线：`pnpm test` 277 文件 / 2,379 通过 / 2 skipped；`tests/eval` 6 文件 / 9 通过。
- 确定性 gate：`pnpm verify:butler` 覆盖规则、项目切换、审批回退，3 场景 / 10 轮全过；断言失败时退出码 1（已反向验证）。
- 入口边界：fixture 模式不跑真实任务与工具；C1 分条、C4 主动推送、跨重启持久化仍由现有测试覆盖。
- 真实模型抽测（`pnpm verify:butler:real`，3 场景 / 9 轮，2026-11-23）：
  - 读 README 并总结：任务完成，回复正确概括项目定位。
  - 切项目后列目录：在 `wechat` 工作区列出 `packages/runtime/src/butler` 前 5 个文件，无 ENOENT。
  - 多轮上下文：第二轮正确回答“渠道层”。
  - 说明：`--real` 默认把任务工作区指向当前仓库；需要隔离时用 `--workspace`。

### Demo 控制台 + Playwright E2E（2026-11-23，第三批）

| 项 | 结果 |
|----|------|
| 本地 demo server | `scripts/demo-server.ts`（`pnpm demo:web`）：仅监听 `127.0.0.1`，自包含 HTML 控制台，代理 chat / approvals / approve / deny / reset；复用 acceptance harness + 脚本化 LLM + 内存 PGlite |
| 装配 | `buildHonoApp` / `AcceptanceApp` 增加 `fetch(req, env)`，供真实 HTTP 服务注入 loopback socket 地址 |
| E2E | `tests/e2e-demo/console.spec.ts`（Playwright，4 用例）：发消息、审批批准、拒绝、重置 |
| CI | `.github/workflows/ci.yml` 新增独立 `demo-e2e` job：安装 chromium → 跑 E2E → 失败上传 `playwright-report/` 与 `test-results/` |

验收证据（2026-11-23 复跑）：

| 项 | 结果 |
|----|------|
| `pnpm test` | 279 文件 / 2,423 通过 / 2 skipped |
| `pnpm test:e2e:demo` | 4 passed（约 12s） |
| `pnpm typecheck` / `pnpm lint` / `pnpm format:check` | 全绿，0 warning |
| 手动冒烟 | `pnpm demo:web` → `/health` 200，控制台页面可加载 |

范围说明：本轮默认只做本地 + CI 的浏览器 demo，不做公网 demo 实例；真实 LLM 可通过 `BUTLER_V5_DEMO_REAL_LLM=1` 接入（见 Phase 4），MCP 未接入。

### Phase 2 C1 + C2（2026-11-23，第四批）

选点来自 [`plans/active/phase2-feature-deepening-2026-11-23.md`](plans/active/phase2-feature-deepening-2026-11-23.md)：
C1 自然语言提醒（[spec](plans/active/phase2-c1-reminders/spec.md)）、
C2 审批前预览（[spec](plans/active/phase2-c2-approval-preview/spec.md)）。

| 项 | 结果 |
|----|------|
| C1 持久化 | `reminders` 表（迁移 0017）+ `ReminderStore`；按状态/时间建索引 |
| C1 工具 | `create_reminder` / `list_reminders` / `cancel_reminder`，仅 `BUTLER_V5_REMINDERS_ENABLED=1` 时注册 |
| C1 到点 | `reminder-worker` 轮询到期提醒 → 复用微信出站纯文本推送；once 完成、daily/weekly 推进；失败保留并冷却重试；迟到写 `reminder.missed` |
| C1 时间 | 固定 `Asia/Shanghai`；非法日期拒绝、过去时间 once 拒绝、重复提醒自动推进 |
| C2 渲染 | `renderApprovalPreview`（纯函数）：`run_command` 全文、`write_file` 相对路径 + 增删行摘要、截断与路径脱敏 |
| C2 链路 | Ask 回复追加预览；等待步骤落库 `preview`；`GET /v1/owner/approvals` 返回 `preview`；开关 `BUTLER_V5_APPROVAL_PREVIEW` 默认关闭 |
| 边界 | 不改审批状态机 / TTL / Grant；关闭开关后行为与旧版本一致 |

验收证据（2026-11-23 复跑）：`pnpm test` 285 文件 / 2,460 通过 / 2 skipped；
`pnpm typecheck` / `pnpm lint` / `pnpm format:check` 全绿，0 warning。
新增用例覆盖：store 持久化、时区/非法日期/过去时间、工具上限与取消、
worker 到点/推进/失败重试/迟到标注、审批预览渲染/截断/路径脱敏/开关回退。

### Phase 2 C3（2026-11-23，第五批）

选点来自 [`plans/active/phase2-feature-deepening-2026-11-23.md`](plans/active/phase2-feature-deepening-2026-11-23.md)：
C3 每周周报（[spec](plans/active/phase2-c3-weekly-digest/spec.md)）。

| 项 | 结果 |
|----|------|
| 统计 | `collectWeeklyDigest` 只读查询 tasks / tracer `run_failed` / audit `approval.requested`，输出完成、待办、失败、审批四项数字 |
| 渲染 | `renderWeeklyDigest` 纯函数；手动 `/周报` 与自动推送共用，空周输出「没有可汇总的记录」 |
| 手动 | `/周报`（别名 `/weekly`）在 LLM 之前拦截，不消耗模型调用 |
| 自动 | `weekly-digest-worker` 按星期 + `HH:mm` + 10 分钟窗口触发；同日 audit 去重；空周不推送 |
| 失败 | 查询/发送失败回复「周报生成失败：<原因>」并写 `weekly_digest.failed` audit |
| 边界 | 默认关闭（`BUTLER_V5_WEEKLY_DIGEST_ENABLED=0`）；无 schema 变更、只读、不改任务/Run/审批状态 |

验收证据（2026-11-23 复跑）：`pnpm test` 288 文件 / 2,480 通过 / 2 skipped；
`pnpm typecheck` / `pnpm lint` / `pnpm format:check` 全绿，0 warning。
新增用例覆盖：四项统计口径与时间窗、空周、渲染结构、手动命令、同日去重、
发送失败/查询失败审计、开关关闭。

---

## Phase 4 — 真实开发能力验证（✅ 2026-11-23，补充验证 2026-11-24）

**目标**：用 Butler / WFXM 通过真实 LLM 从零开发一个实际可用项目，验证
「对话 → 写文件 → 审批 → 运行 → 浏览器验收」闭环。

**选型**：Ledger Lite 本地个人记账 Web 应用（零第三方依赖；Node 内置 HTTP +
JSON 持久化 + 原生前端）。规格与证据见
[`plans/active/phase4-real-project-2026-11-23/spec.md`](plans/active/phase4-real-project-2026-11-23/spec.md)。

| 项 | 结果 |
|----|------|
| 真实模式 | Demo 控制台新增 `BUTLER_V5_DEMO_REAL_LLM=1` + `BUTLER_V5_DEMO_WORKSPACE`；默认脚本模式与 4 个 E2E 不变 |
| 开发过程 | 全程通过浏览器控制台发送需求；`write_file` / `run_command` 逐项审批；真实模型生成 7 个源文件 + 2 个测试文件 + README |
| 项目自测 | 首轮 `npm test`：25 / 25；开放任务新增奶茶账本后 40 / 40 |
| 浏览器验收 | 3 笔录入 → 收入 5,000.00 / 支出 88.50 / 结余 4,911.50；分类筛选 1 行；删除后 2 行且支出 38.50 |
| 导出 | `/api/export.csv` 返回 `text/csv`、正确文件名与 2 行数据 |
| 开放任务 | 仅用模糊需求「加一个奶茶账本」驱动 WFXM 自行实现：首页新增本月杯数 / 花费 / 均价 + 6 个月趋势，新增 15 个测试 |
| 第二项目 | `projects/wakeup-cli`：一句模糊需求 → WFXM 先追问形态与时间 → 自行实现打卡 CLI；打卡 / 改时间 / 连续天数均验证通过，Ledger Lite 未受影响 |
| Git 身份 | 沙箱内注入宿主全局 `user.name/email`，`git init/add/commit` 实测作者正确；新增 4 条单测 |
| 真实微信 | 2026-11-24 10:26 收到 owner 消息，执行 `list_dir projects`，runId `80389008…`，`run.succeeded`；回复列出 7 个项目目录 |
| 网关重启 | 2026-11-24 10:29 重启 `butler-v5-gateway`，`/healthz` 与 iLink 健康检查正常，Git 身份修复已上线 |
| 浏览器真实 LLM 复验 | 2026-11-24：Demo 控制台 4521 真实 LLM 模式，一句模糊需求生成 `projects/water-cli/tools/water-cli/water.js`（282 行），`write_file` + `run_command` 两轮审批均通过；独立复跑 add/today/week/undo/goal/非法输入全部正常；发现沙箱 HOME 为临时目录导致默认数据不跨轮持久化 |
| 真实微信开发闭环 | 2026-11-24：dev_task → 委派 executor → 子代理 `write_file` 待审批 → owner 回「确认」→ `projects/wechat-check/hello3.txt`（内容 `wechat-ok-3`）落盘；子代理审批回退修复生效 |
| 验收 harness 对齐真机 | 2026-11-24：`makeAcceptanceApp` 新增 `intake` 选项，acceptance 可走真实分类/委派路径；新增 2 条确定性用例覆盖默认 dev-session 批量授权、关闭两层开关后的子代理待审批 + 父会话「确认」落盘 |
| Demo 对齐真机 | 2026-11-24：真实模式默认开启 intake 与 subagent worker（`BUTLER_V5_DEMO_INTAKE=0` 可关回）；控制台聊天框支持发「确认」；Playwright 5/5 通过，4521 已重启验证 |
| 回归 | `pnpm test` 2,483 通过；1 个超时用例单独复跑通过；typecheck / lint / format 全绿 |

过程中发现并修复：

1. Node 22 下 `node --test test/` 会把目录当模块，WFXM 将脚本改为
   `node --test test/*.test.js` 后 `npm test` 通过；
2. 奶茶账本首版把 `pad2` 声明在 `state` 之后，初始化触发暂时性死区、首页按钮全部失效；
   用用户口吻反馈「页面没反应、控制台提到 pad2」后，WFXM 将 `pad2` 前移并补注释；
3. 沙箱 HOME 隔离导致 `git commit` 报 `Author identity unknown`，已改为注入宿主全局身份。

遗留 / 后续：wakeup-cli 自动测试已于 2026-11-24 补齐（`apps/cli/test/wakeup.test.mjs`，15 用例全过），
4521 控制台已可直连并完成复跑；CSV 金额
统一两位小数、编辑交易、分页与图表、多用户鉴权仍为可选后续。项目源码位于
[`projects/ledger-lite/`](../projects/ledger-lite/) 与 `projects/wakeup-cli/`。

---

## Phase 5 — 日志与轨迹信息收集体系 P0（✅ 2026-11-24）

**目标**：移动端窄通道下，后台失败/卡住/异常可事后定位。用户只看到
「错误码 + turnId 前 8 位」，Owner 可查全量 trace 与依赖诊断。规格见
[`plans/active/phase5-observability-2026-11-24/spec.md`](plans/active/phase5-observability-2026-11-24/spec.md)。

| 项 | 结果 |
|----|------|
| 错误码 | 新增 `E-LLM-01 / E-CTX-01 / E-TOOL-01 / E-POL-01 / E-RUN-01 / E-DB-01 / E-REQ-01 / E-INT-01` 注册表；未知异常统一 `E-INT-01` |
| 失败信封 | `[E-xxx · turn-172] 处理失败，已记录…`；原始异常/堆栈不再进入回复或 traces |
| turnId 贯穿 | inbound → `routeWechatIntake` / `runButlerLoop` → LLM step trace / 失败 run trace → 子代理 outbox payload / LLM trace → 审批恢复 trace |
| trace 双写 | `trace_events` 表（0018 迁移 + 5 索引）；`LocalTracer` 异步批量 sink（默认 50 条 / 2000ms），失败丢弃不阻塞主流程 |
| 退出与保留 | SIGINT/SIGTERM 先 flush 再关库；启动 + 每小时 prune（默认 30 天 / 20 万行，定时器 `unref`） |
| 健康检查 | `/healthz` 返回 db / outbox / approvals / runs / traces；DB 异常 503；历史无 db 的测试 wiring 降级为 ok |
| Owner 诊断 | 新增 `GET /v1/owner/diagnostics`；`GET /v1/owner/traces` 支持 `turnId` 并优先读持久化表 |
| 边界 | P1 范围见下节：微信诊断/日志指令与导出 CLI 已落地；卡住告警、控制台页、OTLP 外送仍未实现；无新依赖、未新增包 |

验证（2026-11-24）：`pnpm typecheck` / `pnpm lint` 全绿；Phase 5 相关 13 个测试文件
102 用例全部通过（domain error-codes / local-trace、runtime local-tracer、
persistence trace-store / migrations-registry、apps/api diagnostics /
owner-diagnostics / owner-traces / wechat-inbound-butler / wechat-inline-approval /
approval-resume / subagent-worker / routes）。

## Phase 5 — P1 观测入口补强（🟡 2026-11-25 部分完成）

**目标**：让 Owner 无需服务器日志即可自查系统状态与最近轨迹，并把 trace
导出为可附带的 JSONL。

| 项 | 结果 |
|----|------|
| 微信诊断 | `/诊断`（别名 `/diag`）：DB 延迟、待发/失败消息、最久待发、待审批、最近成功运行、trace 内存/待写/已存、保留策略 |
| 微信日志 | `/日志 [n]`（别名 `/logs`，默认 10 条、上限 50）：优先 `traceStore`，无 store 回落内存环形缓冲；每行 `时间 kind/name status [turnId前8位] [错误码]`，不含原始异常 |
| 命名 | `/状态` 已被项目概况占用，系统诊断使用 `/诊断`，避免破坏既有语义 |
| 鉴权 | fail-closed：须配置 `BUTLER_OWNER_WECHAT_ID` 且发件人在名单内；非 Owner 直接放行到普通对话 |
| 导出 CLI | `pnpm trace:export`：`--since/--until`（日期按 Asia/Shanghai 边界）、`--kind`、`--turn`、`--conversation`、`--limit`、`--out`，缺省写 stdout；`TraceListFilter` 增加 `sinceMs/untilMs` |
| 未做 | heartbeat 卡住告警（待阈值/告警渠道/静默期决策，已有 `/healthz` + 诊断兜底）；控制台诊断页（暂无 Web 消费方）；OTLP 外送、抽公共仓库（spec 明示暂缓） |

验证（2026-11-25）：`pnpm typecheck` / `pnpm lint` 全绿；新增
`wechat-observability-commands`（13 用例）、`scripts/trace-export`（7 用例），
`wechat-commands` 补入口链路 2 用例、`trace-store` 补时间窗 1 用例；
`pnpm trace:export` 空库与 `--out` 落盘实测通过。提交 `e9fa18a1`。




