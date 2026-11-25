# Phase 6 — 闭环飞轮体系检查与验证（Spec）

> **状态**：待 owner 批准（不提交、不改代码）
> **日期**：2026-11-25
> **审计基线**：`main` @ `2d69badc`（工作区干净）
> **范围**：六环节 `使用 → 信息收集 → 分析 → 反馈优化 → 测评 → 使用` 是否真实闭环
> **上游**：[`PROGRESS.md`](../../../PROGRESS.md) Phase 1–5、[`ROADMAP.md`](../../ROADMAP.md)、[`HANDOFF.md`](../../../HANDOFF.md)

---

## 1. 结论先行

项目**已经具备六环节的全部"零件"，但不是闭环飞轮，而是"单向数据流 + 人工回填"**。

| 环节 | 能力现状 | 健康度 | 一句话判断 |
|------|----------|--------|-----------|
| 1 使用 | 微信/Slack/Telegram/HTTP/Demo/CLI 入口齐全，命令面丰富 | **强 4/5** | 入口闭环成立 |
| 2 信息收集 | audit_events + trace_events 双写、保留清理、诊断出口齐备 | **强 4/5** | 采集闭环成立，缺告警 |
| 3 分析 | 只有周报 + 会话摘要两处，且周报读内存不读库、默认关闭 | **弱 2/5** | 有分析器，没接在数据上 |
| 4 反馈优化 | 项目管理知识是唯一真回路；记忆确认链被绕过；质量门禁实际跑不起来 | **弱 2/5** | 结构在，触发条件缺失 |
| 5 测评 | 分层测试 + acceptance + 真实 LLM 录音 + release eval-gate | **中 3/5** | 体系在，但 clean HEAD 有红灯、基线陈旧 |
| 6 回流 | 线上 trace 无法自动转回归用例；失败靠人肉看 `/日志` | **弱 1/5** | 最后一公里缺失 |

**总评：10/25，属于"开放回路（open loop）"。** 数据能采到、能被人看到，但"看到之后系统自己变好"这一步几乎全部由人或手工脚本承担。

---

## 2. 审计方法

- 只读代码 + 配置 + 运行态，不修改任何文件；
- 每条结论必须有 `file:line` 证据；
- 区分三态：**已接线并经实测** / **已接线未验证** / **只存在但未接入运行时**；
- 实测命令与结果见 §5。

---

## 3. 六环节审计矩阵

### 3.1 环节 1 — 使用

| 能力 | 证据 | 状态 |
|------|------|------|
| 统一路由入口（healthz / conversations / 三渠道 inbound / WS） | [routes.ts](file:///home/ailearn/projects/WFXM/apps/api/src/routes.ts#L55-L108) | ✅ |
| 渠道入站归一化、顺序、幂等、owner 解析 | [channel-inbound.ts](file:///home/ailearn/projects/WFXM/apps/api/src/channel-inbound.ts#L62-L183) | ✅ |
| 微信 iLink 轮询 + 去重 + 出站 | [ilink-poller.ts](file:///home/ailearn/projects/WFXM/apps/api/src/ilink-poller.ts#L96-L200) | ✅ |
| 自然语言意图分类（chat/dev_task/switch_project/digest…） | [wechat-intake.ts](file:///home/ailearn/projects/WFXM/apps/api/src/wechat-intake.ts#L68-L100) | ✅ |
| 会话快照（待办数/候选数/上次运行） | [wechat-session-snapshot.ts](file:///home/ailearn/projects/WFXM/apps/api/src/wechat-session-snapshot.ts#L42-L94) | ✅ |
| 斜杠命令链（undo/project/task/digest/memory/quality/subagent/observability） | [wechat-inbound-commands.ts](file:///home/ailearn/projects/WFXM/apps/api/src/wechat-inbound-commands.ts#L13-L87) | ✅ |

**缺口**
- ① 没有"纠错/反馈"入口（全仓 `grep 反馈|/feedback|纠错` 在 `apps/api/src` 无命中）。
- ② 命令面只在微信侧；HTTP owner 面没有等价命令，两套口径靠人同步。
- ③ `/诊断` `/日志` 依赖 owner 白名单，非 owner 会话无任何自查手段（设计如此，但属于闭环盲区）。

### 3.2 环节 2 — 信息收集

| 能力 | 证据 | 状态 |
|------|------|------|
| audit_events 写入（普通 + 事务内） | [runtime-store.ts](file:///home/ailearn/projects/WFXM/packages/persistence/src/runtime-store.ts#L453-L500) | ✅ |
| trace_events 持久化（批量 append / list / prune） | [trace-store.ts](file:///home/ailearn/projects/WFXM/packages/persistence/src/trace-store.ts#L100-L131) | ✅ |
| 内存环形 + DB sink 双写 | [bootstrap-wiring.ts](file:///home/ailearn/projects/WFXM/apps/api/src/bootstrap-wiring.ts#L61-L63)、[local-tracer.ts](file:///home/ailearn/projects/WFXM/packages/runtime/src/observability/local-tracer.ts#L95-L149) | ✅ |
| 保留策略（默认 30 天 / 20 万行，每小时 prune） | [index.ts](file:///home/ailearn/projects/WFXM/apps/api/src/index.ts#L254-L268)、[local-trace.ts](file:///home/ailearn/projects/WFXM/packages/domain/src/observability/local-trace.ts#L203-L211) | ✅ |
| 错误码 + turnId 贯通，用户侧不泄漏内部 | [error-codes.ts](file:///home/ailearn/projects/WFXM/packages/domain/src/observability/error-codes.ts) | ✅ |
| 诊断出口 `GET /v1/owner/diagnostics` | [diagnostics.ts](file:///home/ailearn/projects/WFXM/apps/api/src/diagnostics.ts#L85-L172) | ✅ |

**缺口**
- ④ 内存环形只有 500 条（`BUTLER_V5_TRACE_MAX_EVENTS` 默认 500），与 20 万行持久化是两套口径；任何"读内存"的分析都会在繁忙时丢数据。
- ⑤ trace 写入失败只累加 `dropped` 计数（`diagnostics` 可见），**无告警、无渠道推送**（Phase 5 P1 遗留）。
- ⑥ 规则引擎直答、后台 worker（提醒/周报/sweeper）是否 emit trace 未见统一出口，属采集盲区（需在实现时逐点确认，不假设）。

### 3.3 环节 3 — 分析

| 能力 | 证据 | 状态 |
|------|------|------|
| 周报统计（完成/待办/失败/审批） | [weekly-digest.ts](file:///home/ailearn/projects/WFXM/apps/api/src/weekly-digest.ts#L46-L101) | ⚠️ 有实现，口径有洞 |
| 周报定时推送 | [weekly-digest-worker.ts](file:///home/ailearn/projects/WFXM/apps/api/src/weekly-digest-worker.ts#L87-L176) | ⚠️ 默认关闭 |
| 会话摘要投影（Conversation → Summary/Facts/Profile → 记忆） | [butler-runtime.ts](file:///home/ailearn/projects/WFXM/packages/runtime/src/butler/butler-runtime.ts#L213-L276)、[butler-inbound.ts](file:///home/ailearn/projects/WFXM/apps/api/src/butler-inbound.ts#L111) | ⚠️ 需 agent-rag 环境变量，生产未开 |

**断裂点 B-01（P0，最严重）**
周报的"失败次数"读的是**进程内存 tracer**：
`getSharedLocalTracer().list({ limit: 5000 })`（[weekly-digest.ts](file:///home/ailearn/projects/WFXM/apps/api/src/weekly-digest.ts#L71-L80)），而持久化数据在 `traceStore`。
后果：
- 服务重启后"上周失败数"归零；
- 高频时段内存环形只留最后 500 条，统计严重偏低；
- 与 `/日志`、`/v1/owner/traces`（读 `traceStore`，[traces-procedures-tasks.ts](file:///home/ailearn/projects/WFXM/apps/api/src/owner-routes/traces-procedures-tasks.ts#L51)）口径不一致——同一个数字两个答案。

**断裂点 B-02（P0）**
生产环境 `~/.config/butler-v5/env` 未设置 `BUTLER_V5_WEEKLY_DIGEST_ENABLED` / `_TO`，也没有 `BUTLER_V5_MEMORY_PATH` / `BUTLER_V5_OWNER_ID`。
即：**分析环节在真实运行中完全没有运行**（只有手动 `/周报` 可用）。
另外除周报/摘要外，没有错误归因、失败聚类、慢路径分析等任何其他分析器。

### 3.4 环节 4 — 反馈优化

| 能力 | 证据 | 状态 |
|------|------|------|
| Durable Memory 状态机（candidate/confirmed/rejected/expired） | [durable-memory.ts](file:///home/ailearn/projects/WFXM/packages/domain/src/knowledge/durable-memory.ts#L6-L130) | ✅ 结构完整 |
| 去重（trigram Jaccard） | [dedup.ts](file:///home/ailearn/projects/WFXM/packages/domain/src/knowledge/dedup.ts#L42-L80) | ✅ |
| 自动提升 + 回滚 | [auto-promote.ts](file:///home/ailearn/projects/WFXM/packages/domain/src/knowledge/auto-promote.ts#L25-L95) | ⚠️ 默认关闭 |
| 过期清理 sweeper | [candidate-expires-sweeper.ts](file:///home/ailearn/projects/WFXM/apps/api/src/candidate-expires-sweeper.ts) | ⚠️ 默认关闭 |
| 项目管理知识（文档 → 知识 → 注入任务上下文） | [project-knowledge.ts](file:///home/ailearn/projects/WFXM/packages/domain/src/knowledge/project-knowledge.ts#L123-L181)、[project-knowledge-sync.ts](file:///home/ailearn/projects/WFXM/apps/api/src/project-knowledge-sync.ts#L117) | ✅ 生产开启 |
| 显式记忆 `/记住`、"记住：X" | [wechat-memory-commands.ts](file:///home/ailearn/projects/WFXM/apps/api/src/wechat-memory-commands.ts#L164-L210) | ⚠️ 见 B-03 |
| 质量门禁 `/验` `/门禁` | [wechat-quality-gate.ts](file:///home/ailearn/projects/WFXM/apps/api/src/wechat-quality-gate.ts#L134-L190) | ❌ 见 B-04 |
| 自动开发自检 dev-verify | [dev-quality-gate.ts](file:///home/ailearn/projects/WFXM/apps/api/src/dev-quality-gate.ts#L23-L63) | ❌ 见 B-05 |

**断裂点 B-03（P0）**
`/记住` 直接写 `status: "confirmed"`（[wechat-memory-commands.ts](file:///home/ailearn/projects/WFXM/apps/api/src/wechat-memory-commands.ts#L174-L181)），**绕过了 candidate→确认 的整条反馈链**。
同时，生产代码里**没有从对话自动产生 candidate 的路径**（唯一的 `source: "conversation_loop"` 命中是 step input，不是记忆）。真正能造 candidate 的只有 owner HTTP API 和文档提升。
结论：自动提升 / 过期清理 / `/确认记忆` 这些机械装置在真实链路里**长期空转**——系统不会自己"记住教训"。

**断裂点 B-04（P0）**
`config/quality-gate.json` 的 `wechat.cwd` 仍是 `"butler-v5"`（[quality-gate.json](file:///home/ailearn/projects/WFXM/config/quality-gate.json)），但仓库在 Phase 1 已扁平化，`butler-v5/` 目录不存在。
`runQualityGate` 会 `resolve(root, "butler-v5")` 后 `spawn` 到不存在的 cwd → ENOENT → 永远显示"门禁失败"。
同时该文件里的命令指向单个测试文件，不构成项目质量门禁。

**断裂点 B-05（P0）**
生产 `env` 里 `BUTLER_V5_DEV_VERIFY_CMD=["pnpm","exec","vitest","run","apps/api/src/dev-quality-gate.test.ts"]`——**验证命令指向自己的单元测试**，是自指占位，无法验证任何真实项目。
叠加 B-04 的 cwd 解析，WBXM 主线（project `wechat`）的自动 verify 实际不可用。

**断裂点 B-06（P1）**
没有任何"从失败中学习"的机制：dev-verify 失败 / 门禁失败 / 周报失败只产生日志与回复，不生成改进任务、不改配置、不进测评集。

### 3.5 环节 5 — 测评

| 能力 | 证据 | 状态 |
|------|------|------|
| 分层测试（architecture/contracts/integration/trajectories/eval/acceptance/e2e-real） | `tests/` 目录、[ci.yml](file:///home/ailearn/projects/WFXM/.github/workflows/ci.yml#L84-L110) | ✅ |
| Acceptance harness 走真实 `/v1/wechat/inbound`，脚本化 LLM | [harness.ts](file:///home/ailearn/projects/WFXM/tests/acceptance/harness.ts#L2-L16) | ✅ |
| 真实 LLM 录音 + diff | [record-real-llm.ts](file:///home/ailearn/projects/WFXM/scripts/acceptance/record-real-llm.ts#L2-L90)、[diff-real-llm.ts](file:///home/ailearn/projects/WFXM/scripts/acceptance/diff-real-llm.ts#L91-L135) | ⚠️ 基线陈旧 |
| release eval-gate | [release.yml](file:///home/ailearn/projects/WFXM/.github/workflows/release.yml#L44-L87) | ✅ |
| 防作弊（hiddenChecks / tamperPolicy / honestStop / quality） | PROGRESS Phase 2 声称已接入 | ⚠️ 本次未定位到实现文件，需 P0 复核 |

**断裂点 B-07（P0）**
在当前干净 HEAD 上实测 **2 个用例红**：
`apps/api/src/weekly-digest.test.ts` → `records a failed audit when the send fails` / `…when collection throws`。
根因：测试把 `NOW = 2026-11-23T01:00Z` 写死，却用真实时钟调 `listRecentAuditEvents({ windowMs: DAY_MS })`（[weekly-digest.test.ts](file:///home/ailearn/projects/WFXM/apps/api/src/weekly-digest.test.ts#L29-L29)、[L320](file:///home/ailearn/projects/WFXM/apps/api/src/weekly-digest.test.ts#L320-L320)、[L347](file:///home/ailearn/projects/WFXM/apps/api/src/weekly-digest.test.ts#L347-L347)）。日期一过窗口就必挂——是**时间炸弹**，不是业务 bug。
含义：测评体系自身不绿，"全绿"是历史结论而非当前事实。

**缺口**
- ⑧ 真实 LLM recordings 最后更新在 9–10 月（35 个文件），之后模型/提示词已多次变更，baseline 已不代表现状，且没有到期提醒。
- ⑨ acceptance 场景靠手写，`recordings` 是静态 JSON，没有"线上失败 → 新场景"的生成路径。

### 3.6 环节 6 — 回流（测评/线上 → 下一次使用）

| 期望能力 | 现状 | 证据 |
|----------|------|------|
| 线上 trace 自动转回归用例 | ❌ 无 | 仅有手工 `pnpm trace:export`（[trace-export.ts](file:///home/ailearn/projects/WFXM/scripts/trace-export.ts#L1-L50)） |
| 失败驱动 baseline 刷新 | ⚠️ 有脚本无触发 | `record:real-llm` / `diff:real-llm` 需人工执行 |
| 失败对 owner 可见 | ⚠️ 半可见 | `/诊断` `/日志` 需主动查；告警未做；周报默认关 |
| 评测结果回到开发流程 | ⚠️ 人肉 | CI 红灯 → 人改代码，无自动建单 |

**断裂点 B-08（P0）**
闭环最后一公里缺失：从"线上某次失败"到"下次不再犯"之间，没有任何自动化或半自动化通道。这正是飞轮不转的根本原因。

---

## 4. 完善方案

> 原则：先补"断开的线"，再谈"新的轮子"。所有改动小步、可回滚、有单测。

### P0（本阶段必做，让飞轮先转起来）

| ID | 问题 | 改动 | 验收 |
|----|------|------|------|
| **P0-1** | B-07 测评自身红灯 | 修 `weekly-digest.test.ts`：断言窗口改为与 `NOW` 对齐（传 `nowMs` 给查询，或按 `NOW` 计算窗口），消除时间炸弹 | `pnpm exec vitest run apps/api/src/weekly-digest.test.ts` 18/18 绿；`pnpm test` 全绿 |
| **P0-2** | B-01 分析读内存 | `collectWeeklyDigest` 改为优先读 `wiring.traceStore.list({kind:"step"})`（持久化），无 traceStore 时回退内存 tracer；新增"重启后仍统计到失败"单测 | 新增单测：写入 DB → 清内存 → 仍然计数正确；与 `/日志` 口径一致 |
| **P0-3** | B-04 门禁配置陈旧 | `config/quality-gate.json`：`wechat.cwd` 改为 `"."`；`wechat` 命令改为真实门禁（`pnpm typecheck` / `pnpm lint` / 定向 vitest），移除不存在的路径 | 在 WFXM 主线执行 `/验` 返回"全部通过"或真实失败原因；新增 cwd 解析单测 |
| **P0-4** | B-05 自指 verify | `resolveDevVerifyCwd`：当 gate 配置缺失时回退 workspace root（而非拼出不存在路径）；生产 env 的 `BUTLER_V5_DEV_VERIFY_CMD` 改为真实门禁命令（运维动作，文档给步骤，不写死在代码） | 单测覆盖"无配置 → 根目录"；真实运行一次 dev-verify 产出有意义结果 |
| **P0-5** | B-03 记忆链空转 | 让 `/记住` 默认写 `candidate` 并提示"回复「确认记忆」生效"；保留显式 `status=confirmed` 的 owner HTTP 入口作为强制通道。**（决策点：这会改变现有 owner 体感，需批准）** | 单测：`/记住` → candidate；`/确认记忆` 后 → confirmed 且可被召回；与 auto-promote 联调 |
| **P0-6** | B-02 分析不运行 | 文档化并落一份生产开关清单：`BUTLER_V5_WEEKLY_DIGEST_ENABLED=1` + `_TO`；`BUTLER_V5_*_SWEEPER` 按需开启。**只改文档与 env 说明，不擅自改线上** | `docs/ENV.md` 新增"闭环所需开关"小节；`/诊断` 能反映末日推送状态 |
| **P0-7** | B-08 回流缺失 | 新增 `pnpm trace:to-scenario --turn <id>`：读一条 turn 的持久化 trace，生成 acceptance 场景草稿（JSON + 测试骨架）到 `tests/acceptance/scenarios/drafts/`，**不自动入库、不自动改断言** | 脚本对真实 turnId 产出可读草稿；单测覆盖参数解析与输出结构 |

### P1（飞轮加速，可分批）

| ID | 内容 | 验收 |
|----|------|------|
| P1-1 | trace 采集失败告警：`dropped>0` / `pending` 持续超阈值 / outbox failed 经微信推送 owner | 注入故障后收到告警；单测覆盖阈值判定 |
| P1-2 | 分析扩展：失败按 error code × 工具 × 项目聚类，进周报与 `/诊断` | 周报新增一行聚类摘要；单测固定样本断言 |
| P1-3 | 真实 LLM baseline 保鲜：记录日期并在 `/诊断` 暴露"基线年龄"；超过 30 天提示刷新 | 诊断字段可见；过期时提示 |
| P1-4 | 纠错入口：识别"不对/不是这样/错了"→ 生成 candidate + audit，并标记该 turn 进复盘队列 | 单测覆盖识别与写入；不误伤正常对话 |
| P1-5 | 复盘队列：(失败 turn + 相关 trace) → owner 微信卡片 → 一键"转用例/忽略" | 端到端演示一次 |

### 明确不做

- 不引入外部 OTLP exporter / Kafka / 独立 worker 进程（DESIGN §18 未触发）；
- 不做 LLM 自动改提示词 / 自动改配置（无可靠评测，风险高于收益）；
- 不做多租户/商业化相关闭环。

---

## 5. 实测记录（2026-11-25，基线 `2d69badc`）

| 项 | 命令 | 结果 |
|----|------|------|
| 工作区 | `git status --short` | 干净 |
| 网关 | `curl 127.0.0.1:3000/healthz` | `{"status":"ok","wiring":"v5"}` |
| 服务 | `systemctl --user is-active butler-v5-gateway` | `active` |
| 周报单测 | `pnpm exec vitest run apps/api/src/weekly-digest.test.ts` | **2 failed / 16 passed**（B-07） |
| 观测+门禁单测 | `pnpm exec vitest run apps/api/src/wechat-observability-commands.test.ts apps/api/src/wechat-quality-gate.test.ts` | 全过 |
| 生产开关 | `~/.config/butler-v5/env` | 已开：DURABLE_MEMORY / PROJECT_KNOWLEDGE(+WATCH) / SCHEDULE / SUBAGENT / RUN_NOTIFY / INTAKE / DEV_VERIFY；未开：TRACE 保留默认、周报、提醒、auto-promote、candidate-expires、agent-rag memory |

> 注：`systemd` 单元文件里以明文 `Environment=` 写了模型 API Key，属运维安全项，建议迁入 `EnvironmentFile`；本次不改。

---

## 6. 验收标准（本阶段完成定义）

1. `pnpm test` 在干净 HEAD 上 **0 failed**（含 P0-1 修复）；
2. 新增单测覆盖 P0-2 / P0-3 / P0-5 / P0-7；
3. `pnpm typecheck`、`pnpm lint --max-warnings 0`、`pnpm format:check` 全绿；
4. 手工验证：`/周报` 数字与 `/日志`、`/v1/owner/traces` 一致；`/验` 在 WFXM 主线可运行；
5. 文档更新：`docs/PROGRESS.md` 新增 Phase 6 小节，`docs/ENV.md` 增"闭环开关"；
6. 全程不自动提交；改动完成后汇报，由 owner 决定提交。

## 7. 待批准决策点

1. **P0-5** 是否接受"`/记住` 默认写 candidate"这一体感变更？（备选：保持 confirmed，但补一条自动生成 candidate 的对话路径）
2. **P0-6** 是否允许本阶段一并把生产 env 的周报开关打开？（本 spec 默认只写文档，不改线上）
3. 本阶段范围是否只做 P0？P1 是否另起阶段？
