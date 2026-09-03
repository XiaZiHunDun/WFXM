# WFXM BlackBoard State

_last_synced: 2026-09-03 (全面梳理+验收：架构/env/代码健康/全量门禁 4 维全绿；262/1698/3skip)
_handoff: .blackboard/shifts/2026-09-02-d49-exec-audit-handoff.md

## 🧾 全面梳理+验收（2026-09-03，4 维全绿）

- **架构对齐**：无依赖方向违规；副作用咽喉一致（run_command/write_file/send_wechat_file/delegate_to_subagent 均过 capability-boundary+policy-gate）；Model 调用不走策略（预期）；Repository/Model Port 已真实物化（接口+注入点+消费者）；Channel Port 仅 Slack/Telegram 直连 adapter 属已记录实施缝隙，微信走 Port。无新增漂移。
- **env/文档卫生**：p3j-env-audit OK（code/reference/example 对齐）；roadmap P3-2/P3-3/M3 标完成项均有代码+测试落点；port-catalog 与 ports/src 一致；check-dead-env.sh 为 v4 口径脚本报 v5 变量 dead 属工具作用域差异，非回归。
- **代码健康**：无新死代码 / 无超 800 行生产文件 / 无危险非边界 cast（approval-runtime as unknown 为 LLM/JSON 边界正当转换）/ 仅 1 处文档 TODO（tools.ts L498 示例文本）；policy-gate 分支 96.8%、approval ~100%。
- **全量门禁**：typecheck 全包绿 / lint 0 警 / 全量 **262 files / 1698 pass / 3 skip** / deadcode PASS（仅既有 used-in-module 注记）/ file-size+受保护 PASS / contracts 44 PASS / layer-import ENG-15 1458 PASS / p3j-env-audit OK。`main` 干净，无安全/架构硬欠账。

## ✅ P3-3 MCP 首个适配（收口 2026-09-03）

- **核心缺口（本次修复）**：`rejectMcpTokenPassthrough` 此前仅单测引用、未接入任何真实执行路径。真实网络调用唯一咽喉是 `apps/api/src/mcp-bootstrap.ts` 的 `invoke` 闭包。
- **改动**：
  - `domain/governance/mcp-tool-capability.ts` — 新增 `mcpServerDescriptorForInvoke`（构建 invoke 时 guard 所需最小 descriptor）。
  - `apps/api/src/mcp-bootstrap.ts` — `invoke` 闭包对远程 http/sse server 前置 `rejectMcpTokenPassthrough`：服务器未声明 manifest `oauthAudience` 时，拒绝模型提供的凭据类参数（authorization/api_key/bearer/credential/token/password/secret/access_token），fail-closed；stdio 跳过。
  - `apps/api/src/mcp-bootstrap.test.ts` +8（远程无 audience 阻塞 / 带 audience 放行并到 `tools/call`）；`apps/api/src/tool-boundary.test.ts` +1（Child non-owner 无 MCP）。
  - 文档：`docs/config/reference.md` 补 `BUTLER_V5_MCP_MANIFEST_PATH` oauthAudience fail-closed 说明；roadmap `P3.3 MCP 首个适配` 标完成 ✅。
- **P3.3 此前已就绪并本次复核**：具名 registry（`mcpToolsFromServer`/`toMcpCapabilityNameForServer`）、manifest 安装前扫描（`manifest.ts`）、per-server consent（`mcp-consent.ts`）、per-tool ScopedGrant + 卸载吊销（`mcp-grant-lifecycle`）、不可信工具描述（server 默认 risk 权威 `resolveMcpToolRisk`）、Child Run 默认无 MCP（`mcpAllowedForRunSubject`→tool-boundary）。`butler-v5/DESIGN.md` 未动（承重）。
- **门禁**：typecheck 全绿 / lint 0 警 / deadcode PASS（仅既有 used-in-module 注记）/ 全量 **262 files / 1689 pass / 3 skip**（较基线 +4 用例）。

## ✅ P3-2 Capability Provider 申报元数据实装（已收口 2026-09-03，`90e4661d` + `49b14613`）

- **需求**：P3.2 Capability Provider 申报元数据实装（含本地工具重写），为每项能力申报 input/output schema、risk class、sandbox profile、timeout、idempotency、audit policy。
- **改动（主体 `90e4661d`，8 文件 +190/−10）**：
  - `runtime/tool-runtime.ts` — `ToolDefinition` 新增 `readonly declared?: CapabilityProviderMetadata`（类型于 `policy-gate.ts` 定义）。
  - `runtime/capability-boundary.ts` — 新增 `resolveDeclaredMetadata`，按 kind 填充默认：side-effect kind → auditPolicy `full`/idempotent `false`；`command|write` → sandboxProfile `workspace-write-network-deny`；timeoutMs 传播。`capabilityDefinitionFromTool`/`mcpCapabilityProvidersFromTools` 接入。
  - `apps/api/tools.ts` — `enrichDeclaredSchemas` 从 `WEIBUTLER_LLM_TOOLS.parameters` 富化本地核心工具 inputSchema。
  - `apps/api/mcp-tools.ts` — 发现 schema 时随 declared 申报（auditPolicy `summary`）。
  - 测试：capability-boundary +declared 断言扩 95 行；tools/mcp-tools/tool-boundary 各补 inputSchema / resolved-declared 断言。
- **门禁（主体）**：typecheck 全绿；4 个受影响测试文件 60 用例通过；全量 262 文件 / 1685 通过 / 3 skip 无回归。
- **续做（`49b14613`，outputSchema，2 文件 +22/−3）**：`McpDiscoveredTool` 增 `outputSchema`，`makeMcpToolDefinition` 与 inputSchema 一并申报（至少一个 schema 才输出 declared 块）；补一条断言测试。`@butler/api` typecheck 全绿，mcp-tools 5 测试通过。
- **说明**：input/output schema 仅在有真实来源时报（本地核心工具无 outputSchema 来源，不发虚 schema；MCP 是唯一 outputSchema 来源）。

## M3 approval-runtime hardening (merged 2026-09-03)

- Verification: approveWaitingStep idempotent for expired/non-waiting (alreadyProcessed, no double grant); denyWaitingStep via transitionRunToTerminal guard; store stateless -> pending steps fully recoverable.
- Acceptance tests (+132, 3 files): domain types.test.ts +2 (expired/exhausted grant -> Ask deny); runtime approval-runtime.test.ts +2 (fresh store instance resume; restart-then-expired -> no grant, run terminal).
- Test env baseline: bubblewrap slirp integration env-gated (BUTLER_V5_TEST_FULL_SANDBOX=1), default skip; baseline green.
- 5-gate: typecheck green / lint 0 warn / deadcode PASS / file-size PASS / full **263/263 files, 1700 pass, 3 skip**（eval 超时韧性修复后稳定；见下方 eval 段）。
- Noted (untouched): domain/workflows/ unwired but maps to deferred roadmap (DAG/parallel); keep.

## 🎯 eval 场景超时韧性（已收口 2026-09-03）

- **根因**：多轮 eval 场景（05/14/15）每轮重建 PGlite+wiring（migrate ~700ms/轮），全量并行 CPU 争抢下超时；eval/14 是全量唯一不稳定 fail。
- **修复**：eval harness 新增 `makeEvalHarness`/`closeEvalHarness` + `RunScenarioInput.harness`，DB+wiring 建一次跨轮复用；`runEvalScenario` 仅在自有 DB 时 close。
- **效果**：eval/14 6.9s→~2.0s，setup 755ms/轮→0；eval/05 1.18s、eval/15 1.95s；所有 22 个 eval 场景 standalone PASS，typecheck+lint 绿。
- commit `e90609dd`（4 文件 +88/−20）。


**并行开发（2026-09-02 立项；2026-09-02 升级，见 `.blackboard/parallel/README.md`）**：monorepo 按包边界长期并行。各会话开 `par/<area>` topic 分支**自主推进、定期 rebase 自治适配**；**S1 仅在固定汇聚点（里程碑/发布快照）统一 rebase + 解共享冲突 + 全量 5-gate + 合 main**，日常不逐项合。会话：S1 / S2 domain / S3 ports+adapters（已退役主任务）/ S4 persistence / S5 runtime / S6 apps+cli。共享/承重文件（DESIGN/port-catalog/ports index/arch guard/state）仅 S1 可改。

> **2026-09-02 模型升级（业主确认）**：避免"每完成一项就汇聚 → 其他会话空等"。改为——①会话在自己 `par/*` 上推**一批自洽 commits** 再 push，各自跑**本包最小门禁**；②下游定期 `git rebase origin/main` 让上游改动自行流入并**自治适配**；③S1 只做**固定汇聚点**收口（全量 gate 从"每项一次"降到"每批一次"）。

## ✅ 首个汇聚点 M1（已收口 2026-09-02，合 main `89d2c04f`）　→　✅ M2（已收口 2026-09-03，合 main `4a6e628f`）

- **内容**：收口 `par/exec-audit` 在 main（D49）之上的 2 个未并提交：
  1. `bc704b6a` **exactOptionalPropertyTypes 基线清零**（apps/api 10 文件条件展开：wechat-project-surface / dev-quality-gate / schedule-worker / project-state / candidate-expires-sweeper / durable-memory-inject / project-knowledge-inject-sync-watch-worker）——清掉 main 遗留的 `wechat-project-surface.ts:314`（S1 决策登记中的"未清遗留"）。typecheck 全仓归零、lint 0 警、全量回归 1548（唯一 fail = bubblewrap 沙箱基线）。
  2. `dfa7c797` **并行模型升级黑板**（本文件 + parallel/README 的批次汇聚/自治 rebase 规约）。
- **收口结果（S1）**：FF 同步 main 到 D49 → `--no-ff` 合 `par/exec-audit` → 5-gate 全过（typecheck 全绿 / lint 0 警 / 全量 1548 仅 bubblewrap 基线）→ push `a721a90c..89d2c04f`。
- **收口后**：`par/exec-audit` 已消费，勿在其上续开；新会话基于新 main `89d2c04f` 开 `par/*`。

## 🌊 Wave-3 并行分工（S1 下发，2026-09-02）

| 会话 | 分支 | 工作 | 依赖 |
| --- | --- | --- | --- |
| S2 domain | `par/domain-ssot` + cov2/cov3/kcov/refine/status | **SSOT `isTerminalRunStatus`** ✅ **已合入 main `006125b9`**；domain 纯测试补 5 批 — ✅ **M2 合入**（+720 用例/覆盖率） | 完成 |
| S5 runtime | `par/runtime-ssot` + `par/runtime-hardening` | SSOT 消费侧 ✅ `22360a67`；hardening（double-completion 修复 + SSOT cascade fix + 分支覆盖）— ✅ **M2 合入** | S2 已合 ✅ |
| S4 persistence | `par/persistence-clean3` | 包内整理 — ✅ **已合入 main**（in-memory/prod 对齐 S-A~S-H + EventBridge tests + db-open PG skip + cross-impl 线束扩） | 无 |
| S6 apps+cli | `par/api-clean3` | 包内整理 — ✅ **已合入 main M2**（env 去重共享 env-util + 删 7 死导出 + cli lint 门恢复 + exec-audit/CR/tool-profile/test 补覆盖） | 无 |

> **Wave-3 全部完成（M2 已收口 main `4a6e628f`）**。S2 纯测试 5 批与 S5 hardening 因完全独立一并在 M2 收口；S4 persistence 对齐 + S6 apps-cli 整理同步完成。

**当前主线（D49 exec 审计记账）**：owner 重定向——Channel Port 退役（只用微信）；S6 开 exec 行为审计记账；S2/S4/S5 各包"整理与完善"。Wave-2 前半（D48）与 S6 exec（D49）均已并入 main。已并入：
- **D48 / Wave-2 前半（整理类）**：S2 domain `9639d265`（schedule/quiet-reply 边界，vitest 314）、S4 persistence `e7f8a8ed`（修基线 project-knowledge-store.ts:120 exactOptionalPropertyTypes + 边界测试，vitest 108）、S5 runtime `de3da1e2`（终态原子审计 transitionRunToTerminal/withTransaction；denyWaitingStep 走守卫；去 3 处冗余 as；runtime+arch 379）。
- **D49 / S6 exec 审计记账 `22d6691f`**：apps/api 新 `exec-audit.ts`（ExecAuditContext + recordExecAudit 统一落库）；覆盖 workspace-tools（run_command/read_file/write_file 含 bwrap 回退）、mcp-spawn→mcp-bootstrap（spawned）、wechat/dev-quality-gate。事件 `exec.executed`。纯观测、不签发权限、副作用咽喉未变；audit await 修复 PGlite 竞态。10 files +265/−43。

**5-gate（S1 合并后复核）**：D48 3 包 lint 0 警 / 全量 252 pass；D49 lint apps 0 警 / 全量 **253 files / 1545 pass / 1 skip**。多次全量回归仅剩两类环境 fail（cli 符号链伪影、workspace-tools.bubblewrap 缺系统沙箱，均在共享 worktree/沙箱缺依赖，真实生产树正常），无一在本批改动文件。**typecheck 基线遗留已在 M1 分支 bc704b6a 清零**（含原 `apps/api/wechat-project-surface.ts:314`）。

**S1 决策登记**：1. domain `./tools/types.js` 仅 `_archive/contracts` 消费 → **保留**（兼容层，非生产路径）。2. **SSOT isTerminalRunStatus 立项**（Wave-3 协调项，S2+S1 共同提交，勿单会话）。

## 🗑️ domain/workflows 死模块归档（已收口 2026-09-03）

- **处置**：`packages/domain/src/workflows/`（WorkflowState/WorkflowRun/workflowTransition/Channel 抽象）**无生产消费者**（仅 domain barrel 转发），DESIGN/Roadmap 明确 **WorkflowRun 不存在**、Task/Procedure MVP 以 task/procedure 表落地、渠道仅微信（无需多 Channel 抽象）。归档至 [`_archive/packages/domain/workflows/`]（ellet 现有 `_archive/packages/application/_archive/run-workflow` 同惯例）。
- **改动**：git mv → `_archive/packages/domain/workflows/`；`packages/domain/src/index.ts` 删 workflows barrel 转发。tsconfig include 仅 `packages/*/src`，vitest exclude `**/_archive/**` → 归档目录不参与编译/测试收集。
- **门禁**：typecheck 全绿 / deadcode 不再报 workflows / domain+arch 74 文件 580 用例全过 / lint 0 警。
- **遗留观察（未动）**：`packages/domain/src/tools/index.ts` 的 `isToolTimeout/sortToolsByPriority/validateToolDefinition/describeCommandSpec` 仅被自身 barrel+测试引用（ts-prune 报死），但属于 domain/tools 域内 API，需进一步核实后决定归档或保留——本次控制范围未动。

## 🎯 端口物化收尾：文档对齐（已收口 2026-09-03）

- 逐包扫描 9 个 Core Port 生产消费路径后确认：**端口物化现状自洽，无代码缺口**。
  - **Repository Port**：`type RepositoryPort = RuntimeStore`（单一真相源），功能接缝真实（postgres + in-memory 双 impl 过 cross-impl harness），生产经 domain `RuntimeStore` 注入，非休眠接口。
  - **Channel Port**：条件接入符合边界——wechat 被 `wechat-run-notify.ts` 消费（优先 ChannelPort、回退直连 ilink，渐进路径）；slack 经 `channel-outbound.ts`/`routes.ts` 直连绕过 Port。
  - **MemoryService**：trigger-conditioned，MVP 直调 persistence，未物化 = DESIGN §7 正确。
- **修复**：`port-catalog.md` 两处消费路径文档漂移对齐（Repository 行明确"未直接 import、由 domain 合同承载"；Channel 行补充 wechat 已接入、slack 直连绕过的事实）。纯文档，零运行时风险。
- **门禁**：无代码变更，typecheck/lint/测试不受影响。

**下一步**：主循环已全部收口（P3-3 MCP 加固 + P3-2 申报元数据含 outputSchema + M3 审批硬化 + eval 超时韧性 + workflows 归档 + 端口文档对齐 + 完善 wave + **全面验收**），全量 **262 files / 1698 pass / 3 skip** 稳定通过，**全量 5-gate 复核全绿 + 全面验收 4 维全绿**。**无安全/架构硬欠账**。剩余均为延后能力（OCR/embedding/DAG/隔离浏览器/完整审批 UI）或 trigger-conditioned（MemoryService/Channel 统一出站），按 DESIGN §7 与边界规则**不主动立项，等真实触发**。
- **✅ 已决策（2026-09-03）**：domain/tools 4 个纯函数（isToolTimeout/sortToolsByPriority/validateToolDefinition/describeCommandSpec 等）核实后**保留不归档**——整模块被两条约束锁住：① `tests/architecture/section5-domain-pure.test.ts` §5 把 `domain/src/tools/pure.ts` 列为 Policy 纯规则层范围（承重 arch guard）；② `ports/src/r2-shim.ts`（archived contracts compat 层）从 `@butler/domain` 消费 `Tool/ToolCall/ToolResult/DiscoveredTool` types。测试中尝试归档触发 arch guard fail，已完整回退。此决策取代原"是否归档"候选项。

## 不要做

- 改 `wechat-inbound-butler.ts`
- live smoke 升格 PR 硬门槛
- R17 起 v5 AI guard hook 已退役；承重文件改动走 commit review + 5 gate 兜底
- 替未完成会话 commit 共享工作树 WIP（d89385ea 弃稿勿提交，已被 43f8a645/de3da1e2 接管）
- 造"第二实现"仅为可替换而硬物化 Memory/Channel Port

## 上一班

- 2026-09-03 (全面梳理+验收)：架构（无依赖违规、副作用咽喉一致、Repository/Model 已物化、Channel 缝隙为已记录）/ env-文档（p3j-env-audit OK、roadmap 落点对齐）/ 代码健康（无新死代码、无超行文件、无危险 cast）/ 全量门禁（typecheck/lint/262·1698·3skip/deadcode/file-size/contracts 44/layer 1458 全绿）4 维通过。`main` 干净，无安全/架构硬欠账。
- 2026-09-03 (完善 wave 收尾)：实测驱动补齐 policy-gate（`cd70a911`，分支 87.9→96.8%）+ project-knowledge-glob（`08bfde9f`，覆盖 56→96.8%）真实缺口；S2/S4 确认真净、S6 glue 低值不做；**全量 5-gate 复核全绿**（262/1698/3skip，layer ENG-15 1458）。`main` 干净。
- 2026-09-03 (P3-3 收口)：MCP token-passthrough guard 接入真实 invoke 咽喉（`rejectMcpTokenPassthrough` + 新 `mcpServerDescriptorForInvoke`）；远程 http/sse 无 manifest `oauthAudience` → 拒绝凭据类参数 fail-closed；mcp-bootstrap +8 / tool-boundary +1 验收；roadmap P3.3 标完成。全量 262/1689/3skip，typecheck/lint 绿。
- 2026-09-03 (domain/tools 归档核实)：核实 6 个 domain/tools 纯函数均无运行消费者，但整模块被 §5 arch guard（`section5-domain-pure` 锁 `tools/pure.ts`）与 compat 层（`ports/r2-shim` 消费 types）锁住 → **保留，不归档**。尝试归档触发 arch guard fail，已完整回退（源码零净改动）。决策记入"下一步"。
- 2026-09-03 (P3-2 收口 `90e4661d` + `49b14613`)：Capability Provider 申报元数据实装——ToolDefinition.declared + resolveDeclaredMetadata 按 kind 填默认；本地核心工具 inputSchema 自 WEIBUTLER_LLM_TOOLS、MCP 申报 input/outputSchema（outputSchema 续做，MCP 唯一来源）。typecheck 全绿，全量 262/1685/3skip。
- 2026-09-03 (收尾三连)：eval 超时韧性（共享 harness，eval/14 6.9→2s）+ workflows 死模块归档（`_archive/packages/domain/workflows`）+ 端口物化文档对齐（port-catalog Repository/Channel 消费路径）。全量 262/1679/3skipped 稳定通过。
- 2026-09-03 (M3 收口)：审批恢复硬化验收——grant 过期/耗尽决策测试 + 跨重启恢复/重启后过期不恢复测试；bubblewrap slirp env 门控基线归零。5-gate 全过（全量 262/263，仅 eval/14 并行过载超时，单独跑通过）。
- 2026-09-03 (M2 收口)：S1 收口 8 ahead 分支到 main `4a6e628f`——S2 domain 纯测试 5 批 + S5 runtime-hardening + S4 persistence 对齐（S-A~S-H）+ S6 apps-cli 整理。5-gate：typecheck 全绿 / lint 0 警 / 全量回归 259/263（仅 bubblewrap + eval/scenarios 环境基线）。
- 2026-09-02 (SSOT 收口)：S1 合 S2 domain 侧 `006125b9` + S5 消费侧 `22360a67`——SSOT isTerminalRunStatus Wave-3 协调项关闭。domain 25/25、runtime+arch 65/379、全仓 typecheck 全绿。
- 2026-09-02 (M1 收口)：S1 合 `par/exec-audit` 入 main（`89d2c04f`）——exactOptionalPropertyTypes 基线清零 + 并行模型升级黑板。5-gate 全过。Wave-3 分工下发（SSOT S2+S1 / S4 / S6）。
- 2026-09-02 (M1 宣布)：并行模型升级落盘 + 首个汇聚点宣布。见 .blackboard/parallel/README.md。
- 2026-09-02 (D49)：S6 exec 行为审计记账并入（FF 22d6691f）。lint apps 0 警，全量 253/1545。typecheck 基线遗留未清（wechat-project-surface.ts:314）。
- 2026-09-02 (D48 Wave-2 前半)：S1 把关合并 S2 domain + S4 persistence + S5 runtime（整理类）。3 包 lint 0 警，全量仅 3 环境 fail。typecheck 基线 2→1。SSOT isTerminalRunStatus 立项（S2+S1 协调）。
- 2026-09-02 (D47)：见 .blackboard/shifts/2026-09-02-d47-parallel-wave1-handoff.md。
- 2026-09-02 (D46)：Repository Port 物化（in-memory RuntimeStore + ports RepositoryPort；推 D26B §20 #6 原 lock）。
- 2026-09-02 (D45)：owner-routes 按域拆分 7 子模块。

## 🛠 完善 wave（2026-09-03，实测驱动）

- **S5 runtime** `cd70a911`：policy-gate 补 grant sandbox/network 上下文 + mcpReadonlyAutoAllow 分支，分支 87.9→96.8%。
- **S6 apps/api** `08bfde9f`：project-knowledge-glob 补 7 用例（空/traversal/plain/** 双星/scoped/fallback/maxFiles/skip 目录），覆盖 56→96.8% stmts、55→83.3% branch。
- **S2/S4 实测**：domain/persistence 无 <90% stmts、无 <75% branch 文件，确认真净，未强造改动。
- **S6 其余**：低覆盖均为 glue/worker/wiring/route/LLM 接线（wechat-inbound-butler 受保护、subagent/module-worker、owner-routes、approval-resume 等），单测价值低，不做。
- **✅ 全量 5-gate 复核（收尾 2026-09-03，`0779f807` 黑板记录）**：typecheck 全包绿 / lint 0 警 / 全量 **262 files / 1698 pass / 3 skip** / deadcode PASS（domain/tools 死引用为已裁决保留项）/ file-size+受保护文件 PASS / layer-import ENG-15 1458 PASS。无回归、无新欠账，`main` 干净。

## 🧾 换角度验收补遗（2026-09-03，补盲区发现）

> 初轮 4 维全绿之后，从**新角度**（真实运行/供应链/测试质量/安全细节/运营）复核发现 3 个此前未覆盖的项，已对齐处置：

- **① 集成测试环境门控 → 已实证收窄（2026-09-03）**：初判"沙箱/Postgres 从未真跑"过于宽泛。实际本机已验证：**bwrap 基础沙箱（network-deny echo/pwd）通过** + **slirp+allowlist egress Grant（resume）加 `BUTLER_V5_TEST_FULL_SANDBOX=1` 通过**（~120s 冷启动，slirp4netns 在）。仅剩两处真实未验证、且均属主机预置性质：① `healthzUp` 需 `:3000` 跑应用（应用级集成）；② **真实 Postgres 持久化**本机无 PG → `postgresRoundTrip` skip（生产默认 PGlite 已测）。
- **② 元入站异常不隔离 → 瞬时失败丢消息（已修复 `f9a93a99`）**：`runButlerLoop` 原只捕获 `ActiveMainRunConflict`，其他异常（工具抛错/store 失败/backfill 失败）外抛 → Hono 500 → 用户无回复、消息丢。修复：catch 非冲突异常 → logger.error + 返回可用降级 reply（`loop-error` 痕量，原始信息不泄露给用户）。LLM 失败本由 loop 内 `completeWithTimeout` 优雅降级（已确认），此修复兜住剩余传播异常。apps/api 75/474/2skip 无回归。
- **③ run_command 只可操作工作区相对路径（已知权衡，不改）**：`program` 禁 `/` + `ALLOWED_RUN_COMMANDS` 白名单 + 参数禁含 `..`/绝对路径（`workspace-tools.ts`）——安全正确但能力边界窄（`ls /tmp` 等绝对路径被拒）。作为已知限制记入，不改代码。
- **库存修正**：早前误报"无锁文件"——实际 `pnpm-lock.yaml` 存在，供应链锁定健全（`npm audit` ENOLOCK 仅 npm 不读 pnpm 锁）。