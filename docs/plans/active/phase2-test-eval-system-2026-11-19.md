# Phase 2 — 测试与评估体系设计 v2（以使用为中心）

> **状态**：已完成（T1–T8 已交付；评估能力由 Phase 3 扩展） | **日期**：2026-11-19 | **Owner**：主公
> **实现方**：另一 AI 开发工具（只实现，不做产品决策） | **验收方**：我
> **v1**：已被本文件取代（git 历史保留）。v1 的问题是把大量断言放在实现细节上，和 agent 项目的迭代速度冲突。
> **上游依据**：[`../PROGRESS.md`](../PROGRESS.md) · [`../FEATURES.md`](../FEATURES.md) · [`../architecture/wfxm-agent-runtime.html`](../architecture/wfxm-agent-runtime.html)

---

## 1. 核心原则（反脆弱）

agent 的行为主要由模型决定，实现每天都在变。测试只锚定**不随实现变化的东西**：

1. **锚定外部可观察结果**：用户看到的回复、落盘的文件、DB 的终态、调用了哪些工具（集合，不是次数/顺序）、预算上限。
2. **锚定关键节点契约**：工具入参/返回/错误结构、消息规范化结果、状态机迁移、幂等键——这些是跨模型、跨版本稳定的。
3. **锚定真实任务**：用开放任务和端到端场景衡量“有没有解决问题”，允许不同解法。
4. **禁止锚定实现**：内部函数调用顺序、私有字段、精确 prompt 文本、精确 LLM 轮数、精确 tool 参数序列（除非协议要求）。
5. **删测标准**：一条测试如果因合法重构、换模型、换解法而失败，它就在拖后腿，应删除或改写为结果断言。
6. **不为覆盖率保留坏测试**：覆盖率不是门禁；契约与场景才是。

---

## 2. 现有测试审计（314 文件 / 47k 行）

| 类别 | 数量 | 问题 | 处置 |
|------|------|------|------|
| 历史章节守卫 `tests/architecture/section*.test.ts` | 24 | 绑定 DESIGN 章节行号与 D-series 决定；部分（§11 deferred、§15 Effect）已与现状脱节 | **24 → ≤8**：保留结构性不变量，其余删除或并入 |
| 命令级测试 `wechat-*-command*.test.ts` | 5（约 2k 行） | 每个命令一份，样板重复 | 合并为 1 份表驱动，断言命令语义 |
| prompt 文本断言 `wechat-inbound-llm.test.ts` | 1 文件 3 组 | 断言 prompt 包含/不包含具体句子 | 只保留“工具集合包含/不包含” |
| 超大测试 `owner-routes` 1605 行、`wechat-inbound-butler` 1141 行等 | 6 文件 | 一个文件覆盖多种行为，失败定位差 | 按行为拆分，不删语义 |
| 脚本化评估场景 `tests/eval/scenarios` | 22 | 部分断言精确 LLM 调用次数 | 改为结果断言（工具集合、终态、预算） |
| 契约/集成/持久化/沙箱/governance | 其余 | 多数是稳定锚点 | 保留并按 §4 补缺口 |

**保留的结构性守卫（不变量清单，建议 ≤8 条）**

| 不变量 | 现有文件 |
|--------|----------|
| 依赖方向：core 不依赖 adapters/persistence | `dependency-direction.test.ts` |
| 领域层零 IO | `domain-zero-io.test.ts` |
| 应用层边界（routes 只经 ports） | `apps-layer-boundaries.test.ts` |
| workspace 包成员与目录结构 | `package-membership.test.ts` |
| 沙箱进程边界与网络策略 | `workspace-sandbox-arch.test.ts`、`section16-process-boundary`（合并） |
| MCP 契约（manifest/超时/只读） | `mcp-contract.test.ts` |
| 权限不自动授予、子运行不扩权 | `capability-no-auto-grant.test.ts`、`child-run-permission-not-wider.test.ts` |
| 单入口副作用（tool 只能经 boundary） | `side-effect-throat.test.ts`、`single-llm-tool-loop.test.ts` |

> 其余 `section*` 文件先做「不变量映射」：能映射到上表的并入，映射不到的删除；删除必须在 PR 里列出被删文件名与理由，由我复核。

---

## 3. 测试分层（重排）

| 层 | 定位 | 断言方式 | 触发 |
|----|------|----------|------|
| L0 静态 | typecheck / lint / format / 8 条结构不变量 | 确定性 | 每次提交 |
| L1 契约 | 工具、消息、状态机 | 表驱动，结构断言 | PR |
| L2 集成 | inbound HTTP → 管家 → 任务 → DB → reply | 用户可见结果 + DB 终态 | PR |
| L3 轨迹 | 关键节点回归（18 条） | 结果断言（允许不同解法） | PR（标签订阅）/ nightly |
| L4 开放任务 | 真实任务（20 条） | rubric 规则优先 + judge 兜底 | nightly |
| L5 渠道 | L4 smoke + iLink 真机 | 人工/脚本 | 发布前 |

**删除项**：细粒度实现单测（断言内部调用次数、私有字段、精确 prompt、精确参数序列），以及无法映射到不变量/契约/场景的历史守卫。

---

## 4. 关键节点契约（L1，本阶段重点）

### 4.1 工具契约（S1）

一份表驱动 fixture 覆盖全部工具，每个工具至少断言：

| 维度 | 内容 |
|------|------|
| 入参 schema | 必填/可选、类型、默认值、非法输入的错误码 |
| 返回结构 | 成功字段、失败字段、截断标记 |
| 边界 | 路径逃逸、符号链接、超大文件、空目录、不存在路径 |
| 幂等 | 重复调用不产生重复副作用（write/undo/审批） |
| 预算 | 单次调用上限（字节/条目） |

文件建议：`tests/contracts/tools/<tool>.contract.test.ts`，共用 `tests/contracts/tools/fixtures.ts`。

### 4.2 消息与数据类型契约（S2）

按「数据形态 × 层」建矩阵，只断言处理结果，不断言内部路径：

| 形态 | 入站 normalize | 管家路由 | 出站渲染 |
|------|----------------|----------|----------|
| 纯文本 / 超长 / 空 | ✓ | ✓ | ✓ |
| emoji / 混合中英 / 控制字符 | ✓ | ✓ | ✓ |
| 图片 / 文件（含超限、类型不支持） | ✓ | ✓ | ✓ |
| 重复 messageId / 乱序 | ✓ | — | — |
| 非法 JSON body / 缺字段 | ✓ | — | — |

断言：规范化后的字段、错误码、最终回复是否可发送（长度/术语/markdown），不比对完整字符串。

### 4.3 状态与幂等契约（S3）

- Run 状态机：pending → running → succeeded/failed/cancelled，禁止回退；
- Approval：发起/确认/拒绝/重复确认/无待审批；
- 游标：推进即持久化、重启从游标恢复、同 messageId 只处理一次；
- 迁移：空库 → 最新 schema 可启动；旧数据迁移后关键行可读（roundtrip）。

---

## 5. 静态任务轨迹集（收敛到 18 条）

v1 的 36 条按实现分支铺开，维护成本高。收敛为「关键节点 + 高回归价值失败」：

| 分组 | 条数 | 断言重点 |
|------|------|----------|
| 主链路结果 | 4 | 回复满足意图、工具集合包含预期、文件/DB 终态 |
| 消息形态 | 3 | 超长/空/媒体 → 不崩溃且回复可发送 |
| 状态与幂等 | 4 | 重投、并发、审批恢复、撤销 |
| 失败注入 | 5 | LLM 超时/非法 JSON/空响应、工具失败、MCP 超时 → 用户可见说明 |
| 安全 | 2 | 路径逃逸、注入/越权被拒且不泄漏内部信息 |

格式与 runner 由 **agent-eval** 定义（见 §7），WFXM 只提供 fixture：

```jsonc
{
  "id": "traj-004-approval-resume",
  "input": { "turns": ["在 src/a.ts 写入 …", "确认"] },
  "script": [ { "tool": "write_file", "args": { "path": "src/a.ts" } }, { "text": "已写入" } ],
  "expect": {
    "toolSetIncludes": ["write_file"],
    "finalDecisionIn": ["Respond"],
    "files": { "src/a.ts": "export const x = 1" },
    "reply": { "mustMatch": ["已写入"], "mustNotMatch": ["mcp_", "子代理"] },
    "budget": { "maxLlmCalls": 8 }
  }
}
```

**禁止**：`toolSequence: ["a","b","c"]` 这类精确顺序断言、`llmCalls === 2` 这类精确次数断言，除非协议本身要求。

---

## 6. 开放任务集（20 条，唯一质量口径）

- 位置：**agent-eval** 的 `tasks/butler/`（产品输入与 workspace fixture 可引用 WFXM 仓库路径）；
- 结构：`task.json`（任务文本、难度、预算、workspace、rubric 路径）+ `rubric.json`；
- 评分：硬性规则（产物存在/可运行、禁止项、预算）→ 全部通过后进入软性评分（固定 judge 模型、温度 0、双评均值 ≥4）；
- 允许一题多解：只校验「目标达成 + 无禁忌」，不比对具体实现；
- 首轮只记基线（通过率、p50/p95、token 成本），稳定两周后再设门禁。

示例类别：代码理解 4、只读检索 4、小改动 5、多步任务 4、澄清/拒绝 3。

---

## 7. 仓库边界：WFXM vs agent-eval

**判定规则**：换一个 agent 还能用吗？能 → agent-eval；编码了微信/管家行为吗？是 → WFXM。

| 能力 | 归属 | 说明 |
|------|------|------|
| task/trace/score schema、runner、judge、gate、report、flake/成本统计、CLI | **agent-eval** | 已有基础，本阶段扩展 trajectory + open-task |
| 产品任务定义（butler/wechat 场景、rubric）、workspace fixtures | **agent-eval/tasks/butler** | 任务属于评测资产，不散落在产品仓库 |
| adapter（`wfxm-butler.mjs`：启动/驱动/收轨迹） | **agent-eval/adapters** | 已有，补 trajectory/open-task 模式 |
| L1 契约（工具/消息/状态机）、L2 集成、8 条结构不变量 | **WFXM/tests** | 直接 import 源码，快速、PR 必跑 |
| `tests/eval` 22 条 vitest 场景 | **WFXM** | 定位改为「调试用快速确定性回归」，**不参与评分口径** |
| 轨迹 fixture（18 条 JSON） | **WFXM/tests/trajectories** | 数据在 WFXM，执行与判定在 agent-eval |
| L4 smoke（`scripts/l4-smoke.ts`）、iLink 真机 | **WFXM** | 渠道验收属产品 |
| CI 编排 | 各仓库自管 | WFXM 跑 L0–L2；agent-eval nightly 跑 L3–L4 |

**避免双轨**：评分只有 agent-eval 一套；WFXM 的 vitest 场景只用于开发期快速反馈，结果不写入门禁。

---

## 8. 指标与门禁

| 指标 | 口径 | 门禁 |
|------|------|------|
| 结构不变量 | L0 | 100% |
| 契约套件 | L1 | 100% |
| 集成套件 | L2 | 100% |
| 轨迹集 | L3 | 100%（同提交 3 次一致） |
| 开放任务 | L4 | 首轮基线；稳定后 ≥85% |
| 断言稳定性 | 同 commit 重复跑 | 100% 一致（零 flake） |
| 只读任务 p95 | L5 smoke | ≤8s |
| 写入任务 p95 | L5 smoke | ≤25s |
| 内部术语/越权泄漏 | L2–L4 文案断言 | 0 |

---

## 9. 任务拆解（实现方）

| ID | 任务 | 交付物 | 验收 |
|----|------|--------|------|
| T1 | **测试清理**：24 个 section 守卫映射到 8 条不变量；合并命令测试；瘦身 prompt 断言 | PR 说明含「删除清单 + 映射表」 | `pnpm test` 全绿，测试行数下降 ≥15% |
| T2 | 工具契约套件（表驱动，覆盖全部工具） | `tests/contracts/tools/**` | `pnpm exec vitest run tests/contracts/tools` |
| T3 | 消息/数据形态矩阵 | `tests/contracts/messages/**` | 同上 |
| T4 | 状态机/幂等/迁移套件 | `tests/contracts/state/**` | 同上 |
| T5 | 集成主链路（outcome-only） | `tests/integration/**`（≥8 条） | `pnpm exec vitest run tests/integration` |
| T6 | 18 条轨迹 fixture + agent-eval trajectory runner | `tests/trajectories/*.json`、agent-eval `src/trajectory.mjs` | `node src/cli.mjs run --suite trajectory --runtime wfxm-butler` |
| T7 | 20 条开放任务 + rubric + judge + gate 基线 | `agent-eval/tasks/butler/*`、`src/judge.mjs` | `node src/cli.mjs run --suite butler-open` 产出 summary |
| T8 | CI 分层与报告 | WFXM L0–L2 job；agent-eval nightly job + 报告 | 两边 CI 配置通过，报告可读 |

**实现约束**

- 生产代码零改动；发现缺陷单独记录（`docs/plans/active/phase2-findings-2026-11-19.md`），不在本任务修；
- 新测试必须能离线跑（L4 除外），不读真实密钥；
- 单个测试文件 ≤400 行；共享辅助放 `tests/harness/`；
- 每条测试首行注释写「锚定什么不变量/契约/场景」；
- 删除测试必须给出理由，禁止为了绿而放宽断言。

---

## 10. 交接与验收（我执行）

1. 审 T1 的删除清单与映射表，确认没有删掉真不变量；
2. 抽查 10 条新契约测试：是否只断言外部可观察结果；
3. 跑 L0–L3 三次，确认零 flake；统计测试行数变化；
4. 跑 L5 smoke（5+5），确认产品行为未受影响；
5. 抽 5 条轨迹、2 条开放任务人工复核，检查是否「假通过/假失败」；
6. 更新 `docs/PROGRESS.md` 证据并提交。

---

## 11. 风险

| 风险 | 处理 |
|------|------|
| 清理过头，删掉真不变量 | T1 必须逐条映射，我复核后才合并 |
| 开放任务评分不稳 | 规则优先 + 固定 judge + 双评 + 先记基线 |
| 两仓库职责回潮 | 新测试先问「换 agent 能用吗」；评分只认 agent-eval |
| 轨迹集再次膨胀 | 新条目必须对应一个用户可见失败模式，且不能写成精确实现断言 |
