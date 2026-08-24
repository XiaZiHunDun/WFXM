# Butler v5 边界重构后路线图（2026-08）

> **状态**：Active planning  
> **终局**：单用户、可扩展个人管家  
> **边界 SSOT**：[`v5-product-boundaries-2026-08.md`](../decisions/v5-product-boundaries-2026-08.md)  
> **架构事实**：[`v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md)

本路线图不承诺全部实施。P0–P2 是扩大能力前的安全与架构前置；P3–P4 的每个能力仍需单独立项。

---

## P0 — 目标架构与事实收口

**目标**：明确“目标架构”和“当前事实”两种文档职责，并收敛到一个 Run Engine、一个 Policy Gate 和一套 schema。

### 交付

- 新版产品边界成为需求/否决唯一 SSOT；
- `butler-v5/DESIGN.md` 成为务实模块化单体的目标架构 SSOT；
- Conversation / Message / Run / Step / ScopedGrant 是默认内核；Child Run 是普通 Run；Task / Procedure 延后；
- Conversation 无界、Run 有界、同对话主 Run 串行、模型工作集有预算；
- 数据目标改为当前状态 + append-only audit + transactional outbox；
- 旧 v4 边界加 superseded 标记；
- 旧完整函数式设计加 superseded 标记；
- README、AGENTS、handoff 指向 v5；
- 生产调用链与未接线包清单；
- `packages/persistence` 成为唯一 schema；
- 未接线 `packages/application` / `packages/infrastructure` 形成迁移、归档或删除清单；
- v5 保护规则按 [`v5-ai-guard-migration-checklist-2026-08.md`](v5-ai-guard-migration-checklist-2026-08.md) 由人工迁移，再调整 `.cursorrules`。

### 验收

- 新需求不再被引导到 v4 roadmap；
- 新设计不再要求 Effect everywhere、全面 Event Sourcing 或通用 Workflow DAG；
- Subagent、Schedule 都不能创建第二套运行状态机；Procedure 未立项前不得进入默认 schema；
- 文档不再声称生产经过未接线 Effect Application；
- architecture test 能阻止 apps 接入重复 persistence schema；
- 无任何现有生产行为变化。

---

## P1 — 统一 Run、Policy、审批与 ScopedGrant

**目标**：实现“低风险自动、高风险审批、受控长期授权”。

### 1. 统一策略入口

所有父/子 Run 和已注册 Capability 调用统一生成 `ActionRequest`：

```text
subject + capability + resource + context
  → deterministic Policy
  → Allow / Deny / Ask
```

Policy 不由 LLM 分类；模型只能描述意图和请求动作。

### 2. 持久审批

把审批建模为 Run 的 `waiting_approval` Step，不建独立审批聚合：

- pending action digest、原始 runId/stepId 与过期时间写在该 Step 上；
- 待审批列表是查询，不是第二套生命周期；
- Owner 通过微信/CLI/API 批准或拒绝；
- 后续可信 Trigger 恢复原 Run；
- 超时、重复回复和恢复保持幂等；
- 敏感参数只存哈希/摘要，不进普通消息。

P1 同步交付最小 loopback 审批 API/CLI，不建设完整 UI。不可逆动作、凭证、付款、权限变更和首次访问新外部域名必须由该控制面确认；微信只承担低风险确认。

### 3. ScopedGrant

最小字段：

- `subject`
- `capability`
- `scope`
- `expiresAt`
- `usesRemaining`
- `approvalId?`（交互审批生成时指向 waiting Step）
- `delegable`（默认 false）
- `sandboxProfile?`（仅授权提升默认隔离等级时填写）

Run 预算、action digest、policy version 和决策原因进入 Run/Step/Audit 元数据，不在 Grant 重复保存。Owner 可立即撤销 Grant。

### 验收

- 高风险工具未经批准不能执行；
- 批准后仅原 subject、原 capability、原 scope 生效；
- TTL、剩余次数或 action digest 不匹配时拒绝；
- Child Run 不能借父 Grant 扩权；
- 服务重启后 pending approval 可恢复，过期 Grant 不恢复；
- 高风险决策、授权变更、拒绝、越界和外发有不可变审计；低风险成功工具结果只写 Step。

---

## P2 — 执行沙箱与网络边界

**目标**：将“审批允许”与“技术上能做什么”分成两个独立控制面。

### 交付

- 默认低风险 profile：workspace-write + network-deny；
- 文件 scope 与 symlink/realpath 校验统一；
- 命令 runner 支持沙箱 profile，而不是扩大 shell；
- 出网按域名、端口、方法和 TTL 授权；
- 凭证由宿主注入，模型、审计和 context artifact 不可见；
- P2 先定义 Capability Provider 契约骨架；Provider 声明默认 sandbox profile；
- 提升后的 sandbox profile 必须写入短期、不可委派的 ScopedGrant，恢复时重新验证；
- kill switch、超时、进程树清理、输出/磁盘预算。

### 验收

- 即使 Policy 误放行，sandbox 仍阻止 workspace 外写和未授权网络；
- 即使 sandbox 允许，业务高风险动作仍需审批；
- **per-host 出网 allowlist**（第三档 profile）：[`v5-sandbox-network-allowlist-2026-08.md`](v5-sandbox-network-allowlist-2026-08.md) — **P2b/c ✅**；**P2d ✅**（opt-in slirp，见 [`v5-sandbox-p2d-slirp-spike-2026-08.md`](v5-sandbox-p2d-slirp-spike-2026-08.md)）；
- secret 扫描覆盖 prompt、tool result、audit 与 context artifact；
- 崩溃后无遗留子进程和挂载凭证。

---

## P3 — 两条扩展接缝

P3 只建立安全扩展面，不默认安装具体能力。

### 1. Trigger Adapter

- 定义统一 `RunTrigger` 契约，并迁移当前已有的微信、CLI 和 API 入口；
- Webhook、Schedule 和完整本地控制面适配器仍按 P4 分别立项；
- Channel Adapter 负责身份映射、消息标准化、附件接收和回复地址；
- Schedule 只按时产生 Trigger，不拥有 Workflow、Policy 或运行引擎；
- 新入口必须复用 Conversation、Run Engine、Policy 和 Audit。

### 2. Capability Provider

- 扩展 P2 已建立的副作用 Provider 契约骨架，不重新创建接口；
- 文件、命令、MCP、浏览器、出站 Channel 和外部 API 使用同一注册契约；模型走独立 Model Port，不注册为副作用 Capability；
- 每项能力声明 input/output schema、risk class、sandbox profile、timeout、idempotency 和 audit policy；
- 所有副作用都经过 Policy Gate；`Allow` 直接执行，Grant-required / Always-confirm 必须出示 ScopedGrant；
- 卸载 Provider 后相关 Grant 自动失效。

### 3. MCP 首个适配

- 具名 server/tool registry；
- manifest/lockfile 与安装前扫描；
- per-server consent 与 per-tool ScopedGrant；
- 远程 OAuth audience 绑定，禁止 token passthrough；
- 工具描述视为不可信；
- Child Run 默认无 MCP。

### 验收

- 扩展无需改 Run Engine；
- 新入口和新工具不能绕过 P1/P2；
- Trigger 和 Capability 之外不存在第三条扩展接缝；
- 扩展不能创建第二套 Policy、状态机或数据源。

---

## P4 — 条件能力候选

以下候选互不绑定，逐项独立立项。

### 隔离浏览器

> **Owner 2026-08-21：不立项。** 当前 Butler v5 产品无浏览器操控需求；保留为边界上的条件准入项，不在 active backlog。

- Playwright 独立 profile；
- origin allowlist；
- 登录、外发、提交、上传、付款、删除和 ACL 修改即时确认；
- 无宿主 cookie、无公网 CDP。

### 本地控制面

> **Owner 2026-08-21：不立项完整 Web UI。** 审批与运维继续用微信内联确认 + Owner API/CLI；边界上仍属条件准入，有明确场景再议。

- （若将来立项）loopback + pairing/token；
- 在 P1 最小审批 API/CLI 上增加完整 UI；
- 展示 health、runs、approvals、grants、audit 与配置；
- 承担 Always-confirm 动作的权威审批和 Grant 撤销；
- UI 不运行第二套 Run Engine，不直接接触凭证。

### Heartbeat / Schedule Trigger

> **Owner 2026-08-21：已立项 MVP。** 默认关闭；`BUTLER_V5_SCHEDULE_ENABLED=1` + `config/schedule-jobs.json`（或 `BUTLER_V5_SCHEDULE_JOBS`）。

- 只读巡检、提醒、摘要优先（默认 `SCHEDULE_SAFE_TOOL_NAMES`）；
- 产生隔离 Run Trigger（`source=schedule`，subject=`system:scheduler`）；
- 预算、冷却、幂等键、截止时间、quiet success；
- 对话忙 / 主队列忙 / 同进程 in-flight 时 defer；
- 无 ScopedGrant 副作用仍走 Policy Ask（立即停在审批，不扩权）。

### 本地 tracing / 可选 OTEL

> **Owner 2026-08-21：已立项 MVP。** 默认本地；OTEL 仅 stdout JSON lines，无 SDK。

- run/step/capability/policy/grant/approval 事件（审批等待记为 `approval`）；
- 默认本地环形缓冲（`BUTLER_V5_TRACE` 默认开，`=0` 一键停用）；
- 脱敏默认开（`BUTLER_V5_TRACE_REDACT`）；
- exporter opt-in：`BUTLER_V5_OTEL_EXPORTER=stdout`；
- 不把外部 APM 作为运行依赖。

### 文档 ingest 与多模态

> **Owner 2026-08-21：已立项 MVP（文本类具名格式）。** 不做 RAG Studio / 默认全盘索引 / 内嵌 PDF 解析 / OCR。

- 按 provider/格式具名接入：`plaintext`、`markdown`、`pdf`（预提取文本）；
- provenance、大小、截断上限与删除级联（→ Durable Memory by documentId）；
- 工具 `recall_document`；`promote-memory` 生成 candidate；
- 图片 OCR / 向量索引延后，有明确场景再加。

### Durable Memory 基线

> **Owner 2026-08-21：已立项 MVP。** 迁移 `0004_durable_memory.sql`；注入默认关。

- 只区分 Transcript、Durable Memory 和 Project Knowledge（**Project Knowledge MVP ✅ 2026-08-24**，见 [`v5-project-knowledge-proposal-2026-08.md`](v5-project-knowledge-proposal-2026-08.md)）；
- Run 内部压缩产物和滚动摘要不是知识层，也不自动升级为持久记忆；
- Durable Memory 记录来源、置信度、有效期与确认状态（`candidate`/`confirmed`/`rejected`）；
- 删除原始 message 时可 `deleteBySourceMessageId` 同步派生内容；
- 默认结构化/全文（子串）检索 + `recall_durable_memory`；embedding 延后。

### Task / Procedure 基线

> **Owner 2026-08-21：已立项 MVP。** 场景：跨对话待办板 + 可复用线性 runbook；无 DAG。

- Task 是 Owner 可见的持久待办；`POST .../tasks/:id/run` 经 `source=task` Trigger 产生 Run；
- Procedure 是不可变、带版本的线性步骤模板（`when` 仅作标签，MVP 不求值）；无独立运行状态；
- 绑定 Procedure 的 Task 在成功 Run 后推进 `procedureStepIndex`（可用 `advance:false` 关闭）；
- 通用 DAG、并行合并与 Channel reducer 继续延后。

---

## 顺序约束

- P1 未完成，不立项可写 MCP、浏览器动作或长期自治。
- P2 未完成，不开放网络型代码执行或宿主环境 Computer Use。
- P3 未完成，不新增绕过 Trigger/Capability 接缝的入口。
- P4 的 UI、浏览器或 Schedule 不能反向引入第二套 Run Engine、Policy 或数据源。

---

## 明确不进入路线图

- 多租户 SaaS、计费和组织管理；
- 公共插件 Marketplace 自动安装；
- Kubernetes / 默认微服务；
- 无限制 shell 或宿主机 danger-full-access；
- 浏览器端 Agent Runtime；
- Butler v5 当前产品的隔离 Playwright/browser session（Owner 2026-08-21 不立项；见产品边界 Owner 立项记录）；
- 通宵无限循环和无门控 git 修改；
- v4 功能机械搬运或 v5 事件回写 v4。
