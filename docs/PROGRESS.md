# 开发进度台账（阶段记录）

> **用途**：按「阶段」记录开发进度——目标、验收口径、证据、遗留。D-series 单笔 ship 仍记 [`ROADMAP.md`](ROADMAP.md)；架构依据见 [`DESIGN.md`](../DESIGN.md) 与 [`architecture/wfxm-agent-runtime.html`](architecture/wfxm-agent-runtime.html)。
> **更新时机**：阶段开始/结束时；验收证据必须是复跑结果，不引用历史结论。
> **最近更新**：2026-11-19

---

## 阶段总览

| 阶段 | 目标 | 状态 | 验收日期 |
|------|------|------|----------|
| Phase 1 | 主要流程打通，基础功能正常，不报错，无明显消息丢失 | ✅ 完成 | 2026-11-19 |
| Phase 2 | 功能深化（爆点/差异化），按 ROI 选点 | ⏳ 未开始 | — |

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

## Phase 2 — 功能深化（⏳）

入口条件：

1. Phase 1 验收证据保持最新（任一回归先修复）；
2. 从 [`ROADMAP.md`](ROADMAP.md) §4（维度 2）与 [`plans/active/v5-post-boundary-roadmap-2026-08.md`](plans/active/v5-post-boundary-roadmap-2026-08.md) 选定 2–3 个 owner 撞点；
3. 每个选点写明：用户场景、成功判据、失败可见性、回滚方式。

> 阶段结束时新增一节，写清目标、证据（复跑）、闭环问题、遗留，并把总览表状态改为 ✅。
