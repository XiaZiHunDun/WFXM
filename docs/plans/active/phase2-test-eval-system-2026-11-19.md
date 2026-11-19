# Phase 2 — 测试与评估体系设计（任务书）

> **状态**：设计稿（待实现） | **日期**：2026-11-19 | **Owner**：主公
> **实现方**：另一 AI 开发工具（只负责按本文件实现，不做产品决策）
> **验收方**：我（实现完成后做调试、复跑、判定）
> **上游依据**：[`../PROGRESS.md`](../PROGRESS.md) Phase 2 入口 · [`../FEATURES.md`](../FEATURES.md) · [`../architecture/wfxm-agent-runtime.html`](../architecture/wfxm-agent-runtime.html)
> **基线**：Phase 1 验收证据（314 个测试文件 / 2252 通过 / L4 5+5 通过）

---

## 1. 目标与非目标

### 目标

为「微信接入 → 管家层 → 任务层」的每一层、每个模块、每个用户场景建立**可复跑、可判定、可回归**的评估体系，包含三类资产：

| 资产 | 定义 | 判定方式 |
|------|------|----------|
| **测试用例** | 单元 / 契约 / 跨模块集成测试 | 断言（确定性） |
| **静态任务轨迹集** | 固定输入 + 固定 LLM 脚本 + 固定副作用期望，重放用户任务轨迹 | 工具序列、决策、DB 行、文件、预算（确定性，无 LLM 评分） |
| **开放任务集** | 真实自然语言任务，允许模型自由规划 | rubric 评分（规则优先，judge 兜底） |

### 非目标

- 不改产品行为（发现缺陷单独提 issue/commit，不在测试任务里顺手改）；
- 不引入真实外部依赖（GitHub/Todoist 等 MCP）作为 PR 必跑项；
- 不对 open task 做「一次不过就阻断」——先建立基线，再定阈值；
- 不替代 L5 真机渠道验收（iLink 收发仍需人工/脚本真机确认）。

---

## 2. 现状盘点（避免重复建设）

| 资产 | 位置 | 现状 |
|------|------|------|
| 单元/契约测试 | `apps/**/*.test.ts`、`packages/**/*.test.ts` | 300+ 文件，覆盖较全 |
| 架构守卫 | `tests/architecture/`（46 文件） | 依赖方向、包成员、章节不变量 |
| 脚本化评估场景 | `tests/eval/scenarios/`（22 条） | `mock-llm-scripted.ts` + `harness.ts`，已有指标与 painPoints |
| 验收场景 | `tests/acceptance/`（6 文件） | 方法学 / 故障注入 / 多轮 / 产品回归 |
| e2e | `tests/e2e/`（2 文件） | 真实持久化、wiring |
| 渠道前验收窗口 | `scripts/l4-smoke.ts` | 主流程 5 + 可靠性 5，直连 `/v1/wechat/inbound` |
| 真机渠道 | iLink + systemd | 人工确认 |

**主要缺口**

1. 跨模块集成（L2）薄：接入层 ↔ 管家层 ↔ 任务层多为单文件单测，缺「一次消息穿过全链路」的断言；
2. 轨迹集只有 22 条，偏任务层执行，缺接入/记忆/审批/并发/失败注入的系统矩阵；
3. 无开放任务集，无法评估真实任务完成质量；
4. 无统一产物（transcript / 指标 / 分数）与回归对比能力；
5. 失败注入覆盖零散（无统一故障开关）；
6. 无 flake 与成本/延迟门禁。

---

## 3. 被测对象清单（层 / 模块 / 组件）

> 「重点」= 本阶段必须建用例；「已有」= 保留并纳入统一报告。

### 3.1 微信接入层（apps/api）

| 组件 | 关键行为 | 重点 |
|------|----------|------|
| `ilink-poller` / `ilink-sync` | 长轮询、游标持久化、-14 token 过期、重投去重 | 断线/重投/游标 |
| `channel-inbound` / `channel-outbound` | 多渠道鉴权、媒体、出站重试 | 鉴权失败、媒体失败 |
| `routes/inbound` | 共享密钥、body 校验、幂等、工作区边界 | 非法 body / 重放 |
| `ws-routes` / `ws-subscribe` | 订阅、广播、断线 | 断连重连 |
| `dedup-config` | 去重窗口与开关 | 关闭时行为 |
| `channel-media` / `channel-outbound-media` | 图片/文件收发 | 大小/类型/失败 |

### 3.2 管家层（apps/api + packages/runtime）

| 组件 | 关键行为 | 重点 |
|------|----------|------|
| `wechat-intake` / `wechat-intake-llm` / `wechat-intake-corpus` | 意图识别、路由、预算 | 歧义、超长、混合意图 |
| `rule-router` | 确定性规则（帮助、命令） | 规则优先级 |
| `butler-runtime` / `butler-context` | 会话装载、工作集注入 | 冷/热会话 |
| `session-store` / `wechat-session-state` / `wechat-session-snapshot` / `wechat-session-digest` | 会话状态、快照、开场摘要 | 跨会话恢复 |
| `conversation-memory` / `durable-memory-inject` / `wechat-memory-commands` | 记忆写入/召回/去重/隔离 | 三主体隔离、冲突 |
| `wechat-project-switch` / `wechat-project-surface` | 项目切换、项目知识面 | 越权、缺失项目 |
| `wechat-task-commands` / `wechat-subagent-commands` | 任务与子代理命令 | 参数错误 |
| `owner-approval-trigger` / `approval-resume` / `approval-notice` | 审批发起/恢复/通知 | 过期、无待审批、重复确认 |
| `wechat-run-notify` / `wechat-sweeper-notify` | 后台完成/失败推送 | 推送失败、重试 |
| `auto-promote-*` / `candidate-expires-sweeper` | 候选记忆晋级/过期 | 时序 |

### 3.3 任务层（packages/runtime + adapters）

| 组件 | 关键行为 | 重点 |
|------|----------|------|
| `agent-kernel` | 决策循环、轮次上限、终态 | capped / 空响应 |
| `conversation-loop` | 工具调度、持久化、兜底 | unknown tool、解码失败 |
| `pi-task-adapter` | pi 原生 agent 适配 | 事件映射 |
| `delegate-runtime` / `subagent-worker` | 委派、并发、失败口径 | 超轮次、失败可见性 |
| `capability-boundary` / `capability-guard` / `tool-boundary` | 工具可见性、越权拦截 | 提权路径 |
| `approval-runtime` | 挂起/恢复/超时 | 状态机 |
| `workspace-tools` / `workspace-tools-undo` | read/write/list/undo chain | 边界、符号链接、回滚 |
| `adapters/sandbox`（bwrap/slirp） | 隔离、网络白名单、PATH | 逃逸、网络拒绝 |
| `adapters/mcp` + `mcp-*` | 清单、引导、超时、只读策略 | 超时、崩溃恢复 |
| `adapters/llm` + `model-router` | 角色选模、fixture、重试 | 超时、限流 |
| `embeddings` + `knowledge/document-ingest` | 切分、混合检索 | 空文档、超大文档 |

### 3.4 领域 / 持久化 / CLI / 运维

| 组件 | 关键行为 | 重点 |
|------|----------|------|
| `domain/governance` | 策略决策、审批文案 | 风险分级 |
| `domain/memory` | 一致性、supersedes、跨 scope | 冲突合并 |
| `domain/event-sourcing` / `observability` | 事件、指标语义 | 顺序 |
| `persistence/*` | 迁移、事件桥、各类 store | 迁移失败、并发写 |
| `cli` | 登录、诊断 | 参数/退出码 |
| 部署 | health、compose、release | 健康检查语义 |

---

## 4. 用户场景目录（供用例映射）

| # | 场景 | 触发方式 | 期望 |
|---|------|----------|------|
| S1 | 帮助/能力询问 | 文本「帮助」 | 规则回复、无工具 |
| S2 | 只读任务（列目录/读文件/查时间） | 自然语言 | 直接工具调用，低延迟 |
| S3 | 写文件/改代码 | 自然语言 | 审批或委派，落盘可验证 |
| S4 | 多轮上下文（指代、追问） | 连续消息 | 不丢上下文 |
| S5 | 记忆写入与召回 | 「记住：…」/追问 | 落库、按主体隔离 |
| S6 | 项目切换与项目知识 | 「切到项目 X」 | 正确项目面，越权拒绝 |
| S7 | 后台长任务 | 「帮我跑…」 | 受理话术 + 完成/失败推送 |
| S8 | 审批流 | 高风险操作 | 审批文案清晰，确认后执行 |
| S9 | 撤销 | 「撤销」 | 链式回滚正确 |
| S10 | 并发/连发 | 同一/不同会话 | 不丢不重，busy 提示友好 |
| S11 | 断线与重投 | 重启 poller / 重放 messageId | 游标恢复，幂等 |
| S12 | 越权/注入 | 恶意指令 | 拒绝且不泄漏内部信息 |
| S13 | 模型异常 | 超时/非法 JSON/空响应 | 重试→兜底，用户可见说明 |
| S14 | 媒体 | 图片/文件 | 正确接收与回复 |
| S15 | 部署健康 | 冷启动 / 依赖缺失 | 快速失败或降级可见 |

---

## 5. 测试体系分层与执行策略

| 层 | 范围 | 运行时长目标 | 触发 |
|----|------|--------------|------|
| L0 | 静态：lint / typecheck / format / 架构守卫 | < 3 min | 每次提交 |
| L1 | 单元 + 契约 | < 3 min | 每次提交 |
| L2 | 跨模块集成（进程内，真实 store/沙箱可选） | < 5 min | PR |
| L3 | 静态轨迹集（确定性重放） | < 8 min | PR + nightly |
| L4 | 开放任务集（真实模型，rubric） | 20–40 min | nightly / 手动 |
| L5 | 渠道前 L4 smoke + 真机 iLink | 5–10 min | 发布前 |

统一产物目录：`.eval-runs/<runId>/`（已 ignore），包含 `run.json`（环境/版本/seed）、`results.json`、`report.md`、失败转录。

---

## 6. 静态任务轨迹集（Trajectory Set）设计

### 6.1 文件格式

```jsonc
{
  "id": "traj-014-write-approval",
  "title": "高风险写入触发审批并恢复",
  "layer": "L3",
  "tags": ["tools", "approval", "recovery"],
  "seed": 42,
  "turns": [
    { "user": "在 src/a.ts 写入 export const x = 1", "llm": [ { "tool": "write_file", "args": { "path": "src/a.ts" } } ] },
    { "user": "确认", "llm": [ { "text": "已写入" } ] }
  ],
  "expect": {
    "toolSequence": ["write_file"],
    "decisions": ["Ask", "Respond"],
    "files": { "src/a.ts": "export const x = 1" },
    "db": { "runs": 1, "approvals": 1 },
    "budget": { "maxLlmCalls": 6, "maxToolCalls": 3 },
    "reply": { "mustMention": ["已写入"], "mustNotMatch": ["mcp_", "子代理"] }
  }
}
```

- 复用 `tests/eval/mock-llm-scripted.ts` 的适配器形态；LLM 脚本只是「固定响应序列」，不是录制的真实输出；
- 断言只允许**确定性事实**：工具调用序列、终态决策、DB 行数/关键字段、文件内容、预算上限、用户可见文案不变量；
- 不允许在轨迹集里调用真实模型、真实网络、真实微信。

### 6.2 覆盖矩阵（首批 36 条）

| 维度 | 条数 | 示例 |
|------|------|------|
| 主流程 happy path | 6 | 帮助、读文件、列目录、写文件、长回复、混合工具 |
| 多轮与上下文 | 5 | 指代、主题切换、超长历史压缩、双会话隔离、工作集预算 |
| 审批与治理 | 5 | 高风险写、审批拒绝、重复确认、无待审批、审批后恢复 |
| 记忆 | 5 | 写入/召回、去重、跨主体隔离、冲突 supersede、召回为空 |
| 并发与幂等 | 5 | 同会话并发、跨会话并发、重投回放、连续三条、busy 拒绝 |
| 失败注入 | 6 | LLM 超时、非法 JSON、空响应、工具异常、MCP 引导超时、推送失败 |
| 安全 | 4 | 路径逃逸、工具越权、prompt 注入、内部术语泄漏 |

### 6.3 运行与判定

```bash
npx tsx tests/harness/run-trajectories.ts --all            # 全部
npx tsx tests/harness/run-trajectories.ts --tag approval   # 按标签
npx tsx tests/harness/run-trajectories.ts --id traj-014    # 单条
```

退出码：任一条失败即 1；输出 `failed` 明细与首次差异（期望 vs 实际）。

---

## 7. 开放任务集（Open Task Set）设计

### 7.1 任务定义

`tests/open-tasks/<id>.task.md` 头部 YAML：

```yaml
id: open-003-refactor
difficulty: medium          # easy | medium | hard
timeoutSec: 240
budget: { maxToolCalls: 20, maxTokens: 60000 }
workspace: fixtures/refactor-small   # 任务开始时复制到隔离目录
rubric: rubrics/open-003.json
```

正文 = 用户口吻的任务（允许模糊，模拟真实微信输入）。

### 7.2 评分规则（rubric）

规则优先，judge 兜底：

1. **硬性**：产物存在且可运行（文件/命令/测试）、必须命中的工具类别、禁止出现的内部术语/越权操作；
2. **软性**：完成度、解释清晰度、是否多问不必要问题（由固定 judge 模型按 1–5 打分，双评取均值，阈值 ≥4）；
3. **成本/延迟**：超出预算直接判失败；
4. 任一硬性失败 → 该任务 0 分，不进入软性评分。

### 7.3 首批 20 条

| 类别 | 条数 | 示例 |
|------|------|------|
| 代码理解 | 4 | 解释某模块职责、找调用链、定位配置 |
| 只读检索 | 4 | 列子包、找文件、读日志摘要、查文档 |
| 小改动 | 5 | 加测试、改文案、修 typo、加只读工具命令 |
| 多步任务 | 4 | 写脚本+运行+报告、批量改名、迁移小模块 |
| 失败与澄清 | 3 | 信息不足时提问、无权限时说明、任务不可行时拒绝 |

### 7.4 运行与报告

```bash
npx tsx tests/harness/run-open-tasks.ts --set smoke     # 5 条快速集
npx tsx tests/harness/run-open-tasks.ts --set full      # 20 条
```

产物：每条 `transcript.json`、`score.json`（硬性/软性分项）、`diff.patch`（若改文件）；汇总 `summary.json`（通过率、p50/p95 延迟、token 成本、失败聚类）。

---

## 8. 指标与门禁

| 指标 | 采集 | 初始门禁 |
|------|------|----------|
| 确定性套件通过率 | L0–L3 | 100% |
| flake 率（同提交 3 次） | 随机抽 20 条重跑 | ≤ 2% |
| 工具错误率 | 轨迹集统计 | ≤ 1% |
| 内部术语/markdown 泄漏 | 轨迹 + open task 文案断言 | 0 |
| 只读任务 p95 | L4 smoke / 轨迹计时 | ≤ 8s（本机基线） |
| 写入任务 p95 | 同上 | ≤ 25s |
| open task 通过率 | nightly | 首轮只记基线，稳定 2 周后设 ≥ 85% |
| token 成本/任务 | open task | 记录基线，超基线 30% 告警 |

CI：PR 跑 L0–L3；nightly 跑 L3+L4 并上传 `.eval-runs` 产物；L5 由我手动在发布前执行。

---

## 9. 任务拆解（交给实现方）

> 每项完成即自测并提交；不得改动生产行为。若发现产品缺陷，单独记录到 `docs/plans/active/phase2-findings-<date>.md`，不要在本任务内修。

| ID | 任务 | 交付物 | 验收命令 |
|----|------|--------|----------|
| T1 | 统一测试基础设施：runId、seed、产物写入、失败差异输出 | `tests/harness/runtime.ts`、`tests/harness/artifacts.ts`、单测 | `pnpm exec vitest run tests/harness` |
| T2 | 轨迹集 schema + runner | `tests/trajectories/schema.ts`、`tests/harness/run-trajectories.ts` | 用 2 条样例轨迹跑通 |
| T3 | 轨迹集 36 条（按 §6.2 矩阵） | `tests/trajectories/*.json` | `npx tsx tests/harness/run-trajectories.ts --all` 全绿且 3 次稳定 |
| T4 | 跨模块集成套件（接入↔管家↔任务） | `tests/integration/*.test.ts`（≥12 条） | `pnpm exec vitest run tests/integration` |
| T5 | 持久化/恢复套件：迁移、事件桥、重启恢复、并发写 | `tests/persistence/*.test.ts`（≥8 条） | 同上 |
| T6 | 失败注入框架：统一故障开关（LLM/工具/MCP/推送/DB） | `tests/harness/faults.ts` + 接线说明 | 轨迹集中 failure 标签全绿 |
| T7 | 开放任务集 harness + 20 条 + judge + 评分 | `tests/open-tasks/**`、`tests/harness/run-open-tasks.ts` | smoke 5 条产出 `summary.json` |
| T8 | 报告与门禁：汇总报告、PR/nightly CI 配置、flake 检测脚本 | `.github/workflows/eval.yml`、`tests/harness/report.ts` | CI 配置校验通过；本地跑出 `report.md` |

**实现约束**

- 测试必须离线可跑（open task 除外），不得读取 `~/.config` 真实密钥；
- 不引入新的大型依赖；如需新增，先写理由到任务 PR 描述；
- 单文件 ≤ 400 行；测试辅助代码放 `tests/harness/`；
- 所有新测试首行注释写明「断言什么、为什么」；
- 每个套件必须能在 CI 的 25 分钟 job 内跑完（L4 单独 nightly）。

---

## 10. 交接与我的验收流程

1. 检查 diff：只新增测试/文档/CI，无生产代码改动；有则要求拆分；
2. 本地复跑 `pnpm typecheck && pnpm lint && pnpm format:check && pnpm test`；
3. 跑 L3 三次，确认无 flake；抽查失败信息是否可定位；
4. 跑 L4 smoke 5 条，核对产物与成本；
5. 跑 `scripts/l4-smoke.ts` 主流程+可靠性，确认未被测试基建影响；
6. 随机抽 5 条轨迹 + 2 条开放任务人工审阅断言质量（是否「假通过」）；
7. 更新 `docs/PROGRESS.md` 证据行并提交。

---

## 11. 风险与开放问题

| 风险 | 处理 |
|------|------|
| 轨迹集退化为「复述实现」 | 断言只写用户可见结果与外部副作用，不写内部函数细节 |
| open task 评分不稳定 | 规则优先；judge 固定模型+低温度；双评取均值；先记基线 |
| 真实模型成本 | nightly 限 20 条 + 预算上限；本地默认只跑 smoke |
| 沙箱/网络导致 flake | 确定性套件禁网；沙箱用例固定 profile 与 PATH |
| 测试基建侵入产品 | 仅通过现有 ports/注入点接线；禁止在 src 中加 `if (test)` 分支 |
