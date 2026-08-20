# Butler v5 边界重构后路线图（2026-08）

> **状态**：Active planning  
> **终局**：单用户、可扩展个人管家  
> **边界 SSOT**：[`v5-product-boundaries-2026-08.md`](../decisions/v5-product-boundaries-2026-08.md)  
> **架构事实**：[`v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md)

本路线图不承诺全部实施。P0–P2 是扩大能力前的安全与架构前置；P3–P4 的每个能力仍需单独立项。

---

## P0 — 事实与治理收口

**目标**：只有一个边界入口、一张生产调用图和一套生产数据库 schema。

### 交付

- 新版产品边界成为需求/否决唯一 SSOT；
- 旧 v4 边界加 superseded 标记；
- README、AGENTS、handoff 指向 v5；
- 生产调用链与未接线包清单；
- `packages/persistence` 成为唯一 schema；
- 未接线 `packages/application` / `packages/infrastructure` 形成迁移、归档或删除清单；
- v5 保护规则按 [`v5-ai-guard-migration-checklist-2026-08.md`](v5-ai-guard-migration-checklist-2026-08.md) 由人工迁移，再调整 `.cursorrules`。

### 验收

- 新需求不再被引导到 v4 roadmap；
- 文档不再声称生产经过未接线 Effect Application；
- architecture test 能阻止 apps 接入重复 persistence schema；
- 无任何现有生产行为变化。

---

## P1 — 统一 Policy、审批与 Capability Lease

**目标**：实现“低风险自动、高风险审批、受控长期授权”。

### 1. 统一策略入口

所有父/子工具、Channel 发送、定时任务、MCP 和浏览器动作统一生成 `ActionRequest`：

```text
subject + capability + resource + context
  → deterministic Policy
  → Allow / Deny / RequireApproval
```

Policy 不由 LLM 分类；模型只能描述意图和请求动作。

### 2. 持久审批

将当前 AskApproval 回显升级为：

- `ApprovalRequested` 事件；
- pending action 与参数摘要；
- Owner 通过微信/CLI/API 批准或拒绝；
- 通过 correlation/causation 恢复原 action；
- 超时、重复回复和重放保持幂等；
- 敏感参数只存哈希/摘要，不进普通消息。

### 3. Capability Lease

最小字段：

- `leaseId`
- `subject`
- `capability`
- `scope`
- `issuedAt` / `expiresAt`
- `maxCalls` / `callsUsed`
- `budget`
- `delegable`
- `issuer`
- `approvalFingerprint`
- `policyVersion`
- `revokedAt`

支持 once、turn、session、TTL、until-revoked；Owner 可立即撤销。

### 验收

- 高风险工具未经批准不能执行；
- 批准后仅原 subject、原 capability、原 scope 生效；
- TTL、次数、预算、策略版本或 fingerprint 不匹配时拒绝；
- 子代理不能借父 lease 扩权；
- 服务重启后 pending approval 可恢复，过期 lease 不恢复；
- 每次决策和执行都有事件与审计记录。

---

## P2 — 执行沙箱与网络边界

**目标**：将“审批允许”与“技术上能做什么”分成两个独立控制面。

### 交付

- 默认 A1：workspace-write + network-deny；
- 文件 scope 与 symlink/realpath 校验统一；
- 命令 runner 支持沙箱 profile，而不是扩大 shell；
- 出网按域名、端口、方法和 TTL 授权；
- 凭证由宿主注入，模型、事件和 snapshot 不可见；
- sandbox manifest 与 lease 绑定，恢复时必须重新验证；
- kill switch、超时、进程树清理、输出/磁盘预算。

### 验收

- 即使 Policy 误放行，sandbox 仍阻止 workspace 外写和未授权网络；
- 即使 sandbox 允许，业务高风险动作仍需审批；
- secret 扫描覆盖 prompt、tool result、audit、event 与 snapshot；
- 崩溃后无遗留子进程和挂载凭证。

---

## P3 — 可插拔能力底座

P3 只建立安全扩展面，不默认安装具体能力。

### 1. MCP Client

- 具名 server/tool registry；
- manifest/lockfile 与安装前扫描；
- per-server consent 与 per-tool lease；
- 远程 OAuth audience 绑定，禁止 token passthrough；
- 工具描述视为不可信；
- child 默认无 MCP。

### 2. Channel Adapter

- 统一 inbound identity、pairing、conversation 与 Policy；
- 微信保持首要入口；
- 第二 Channel 必须单独 threat model；
- 禁止匿名公网入口和群聊默认高权限。

### 3. 本地控制面

- loopback + token；
- 展示 health、events、approvals、leases、audit 与配置；
- 可批准、拒绝和撤销；
- UI 不运行第二套 Loop，不直接接触凭证。

### 验收

- 扩展无需改主 Loop；
- 新入口和新工具不能绕过 P1/P2；
- 卸载扩展后 lease 自动失效；
- 控制面被关闭时微信主路径不受影响。

---

## P4 — 条件能力候选

以下候选互不绑定，逐项独立立项。

### 隔离浏览器

- Playwright 独立 profile；
- origin allowlist；
- 登录、外发、提交、上传、付款、删除和 ACL 修改即时确认；
- 无宿主 cookie、无公网 CDP。

### Heartbeat / Cron

- 只读巡检、提醒、摘要优先；
- 隔离 conversation；
- 预算、冷却、幂等键、截止时间、quiet success；
- 主队列忙时 defer；
- 无租约副作用立即停止。

### 本地 tracing / 可选 OTEL

- run/turn/tool/handoff/policy/approval/lease span；
- 默认本地；
- exporter opt-in，可脱敏，可一键停用；
- 不把外部 APM 作为运行依赖。

### 文档 ingest 与多模态

- 按 provider/格式具名接入；
- provenance、大小、成本、数据驻留和删除策略；
- 不演化为 RAG Studio 或默认全盘索引。

---

## 顺序约束

- P1 未完成，不立项可写 MCP、浏览器动作或长期自治。
- P2 未完成，不开放网络型代码执行或宿主环境 Computer Use。
- P3 未完成，不新增多个各自实现认证/审批的入口。
- P4 的 UI、浏览器或调度不能反向引入第二套 Loop、Policy 或数据源。

---

## 明确不进入路线图

- 多租户 SaaS、计费和组织管理；
- 公共插件 Marketplace 自动安装；
- Kubernetes / 默认微服务；
- 无限制 shell 或宿主机 danger-full-access；
- 浏览器端 Agent Runtime；
- 通宵无限循环和无门控 git 修改；
- v4 功能机械搬运或 v5 事件回写 v4。
