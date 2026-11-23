# 开发进度台账（阶段记录）

> **用途**：按「阶段」记录开发进度——目标、验收口径、证据、遗留。D-series 单笔 ship 仍记 [`ROADMAP.md`](ROADMAP.md)；架构依据见 [`DESIGN.md`](../DESIGN.md) 与 [`architecture/wfxm-agent-runtime.html`](architecture/wfxm-agent-runtime.html)。
> **更新时机**：阶段开始/结束时；验收证据必须是复跑结果，不引用历史结论。
> **最近更新**：2026-11-23

---

## 阶段总览

| 阶段 | 目标 | 状态 | 验收日期 |
|------|------|------|----------|
| Phase 1 | 主要流程打通，基础功能正常，不报错，无明显消息丢失 | ✅ 完成 | 2026-11-19 |
| Phase 2 | 功能深化（爆点/差异化），按 ROI 选点 | 🚧 进行中（测评体系已完成） | — |
| Phase 3 | 功能打磨：地基 → 楼层 → 体验 | ✅ 完成（任务层 / 管家层 / 渠道与产品能力） | 2026-11-23 |

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
| 乱序到达 | 未覆盖；需要会话内序号或时间窗机制 |
| 审批超时过期 | 当前无 TTL 机制，仅测了「无待审批」路径 |
| capped 分支 | 模型未跑满 12 轮，真机只验证了推送通道，判定本身仍靠单测 |
| compose 启动告警 | `POSTGRES_PASSWORD missing`，容器已在运行故不影响，但首次全新部署需补齐 |
| 本机 SSH 代理 | `127.0.0.1:7890` 不可用时 push 需 `ProxyCommand=none` |

---

## Phase 2 — 功能深化（🚧）

> 本阶段包含两块：**测试与评估体系**（✅ 已收尾）与**功能深化（爆点/差异化）**（未开始，需从 ROADMAP §4 选定 2–3 个 owner 撞点）。首块任务书见 [`plans/active/phase2-test-eval-system-2026-11-19.md`](plans/active/phase2-test-eval-system-2026-11-19.md)。
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

> 阶段结束时新增一节，写清目标、证据（复跑）、闭环问题、遗留，并把总览表状态改为 ✅。

---

## Phase 3 — 功能打磨（✅ 2026-11-23；任务层地基 ✅ 2026-11-20、管家层 ✅ 2026-11-23、渠道与产品能力 ✅ 2026-11-23）

> 任务层 B1–B10、管家层 B11–B16、渠道与产品能力 C1–C6 均已交付。C3 按决策保持旧入口为生产默认，未做渠道 cutover；遗留项见阶段收尾。

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

### 遗留与风险（不阻塞 Phase 3）

| 项 | 说明 |
|----|------|
| 进程内并行 | 全局锁为 FIFO 串行；真正的并行需多 worker / 多进程设计 |
| 429/5xx 重试 | 委托 `retryAssistantCall`，未新增网络级重试用例 |
| judge 严格模式 | 仍为 observe，稳定后再转 `--judge` |

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

阶段结论：任务层、管家层、渠道层与产品能力打磨完成；C3 按决策保持旧入口为生产默认，未做 cutover。

遗留与风险（不阻塞，需单独立项）：

| 项 | 说明 |
|----|------|
| 渠道 cutover | Slack/Telegram/generic 仍走旧引擎；前置：管家补齐撤销/诊断、per-channel 灰度与回滚、契约测试 |
| 管家能力面 | 撤销/重试/诊断/质量门/子代理仅在旧入口，管家路径不可达 |
| ChannelPort 契约 | 空文本/超长/超时语义未统一，暂由各适配器防御性裁剪 |
| 进程内并行 | 全局锁为 FIFO 串行；真正的并行需多 worker / 多进程设计 |
| 429/5xx 重试 | 委托 `retryAssistantCall`，未新增网络级重试用例 |
| judge 严格模式 | 仍为 observe，稳定后再转 `--judge` |
