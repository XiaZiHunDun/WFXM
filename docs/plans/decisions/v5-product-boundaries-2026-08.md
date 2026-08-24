# Butler v5 产品边界（2026-08）

> **状态**：Accepted  
> **产品终局**：单用户、单信任域、自托管的可扩展个人 AI 管家  
> **默认风险姿态**：低风险自动执行；高风险即时审批；受控能力可签发可撤销的 ScopedGrant
> **取代**：[`roadmap-backlog-and-boundaries-2026-05.md`](roadmap-backlog-and-boundaries-2026-05.md) 作为需求、否决与立项的唯一入口  
> **目标架构**：以 [`../../../butler-v5/DESIGN.md`](../../../butler-v5/DESIGN.md) 为准
> **架构现实**：以 [`v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md) 为准

---

## 1. 为什么重写

旧边界形成于 Butler v4 仍是主线的 2026-05，依赖以下前提：

- 入口主要是微信；
- 会话事实源是 JSONL，SQLite 只做派生查询；
- Python v4 的九层实现、开关与本地文件队列是当前能力；
- 浏览器、UI、MCP、定时自治等只能靠扩大默认信任面实现。

这些前提已经失效。v4 于 2026-08-16 退役，v5 是唯一产品主线。当前已实现能力、存储和入口只由生产架构文档声明；本文件不复制能力清单。

因此，新边界不再按技术名词整类否决，而按**产品契合度、风险、授权范围和运行隔离**裁决。

---

## 2. 终局公理

所有边界必须能从以下公理推导，不能推导的“禁止项”不得继续作为硬边界：

1. **单 Owner、单信任域**：Butler 服务一个 Owner，不是共享 Gateway 或多租户 SaaS。
2. **自托管优先**：默认部署在 Owner 控制的单机环境；云服务是适配器，不是控制权来源。
3. **LLM 是不可信规划器**：模型可以提出动作，不能自行获得权限、凭证或绕过 Policy Gate / Provider Boundary。
4. **能力面可以扩展，授权面必须收敛**：新 Channel、MCP、浏览器和调度可以接入，但只能获得具名、限域、限时、可撤销的 ScopedGrant。
5. **事实可审计**：重要状态与副作用必须有可追踪审计、审批、ScopedGrant 和结果。
6. **生产路径优先于愿景脚手架**：文档描述当前真实调用链；未接线原型不能算已交付能力。

---

## 3. 裁决流程

```text
新需求
├─ 破坏单 Owner / 自托管 / LLM 不可信？ ── 是 ─► 硬边界：拒绝
├─ 涉及写入、外发、越界、提权、网络或不可逆动作？
│  └─ 是 ─► Policy → Approval → ScopedGrant → Provider Boundary → Audit
├─ 能否用具名工具、路径、域名、Server 或 Channel 限定？
│  ├─ 是 ─► 条件准入或按需立项
│  └─ 否 ─► 拒绝，直到能表达最小权限
└─ 纯读取或低风险沙箱内动作 ─► 可默认自动执行
```

“已有 SDK”“外部产品已实现”或“模型认为安全”都不是准入理由。

---

## 4. 硬边界

以下边界继续成立，除非 Owner 通过新 ADR 改变产品终局。

### 4.1 产品与部署

- 不做多租户 SaaS、计费、组织管理或共享信任域。
- 不以 Kubernetes、网络微服务或多实例消息集群为默认部署目标。
- 不把 Butler 变成公开插件市场、RAG Studio、IDE 或通用低代码 Agent 平台。
- v5 是唯一活动主线；v4 不恢复为平行产品，也不做 v5→v4 事件反向同步。

### 4.2 权限与安全

- LLM 不得直接访问凭证、数据库连接、宿主文件系统、Channel 发送接口或提权接口。
- 所有 Trigger 与所有 Capability 调用必须共用同一个 Run Engine、Policy Gate 和 Audit 路径。
- 禁止 LLM 自行扩权；子代理不继承父代理全部权限，且默认不可再委派。
- 禁止未解析 shell 字符串、`shell: true` 和默认 unrestricted host execution。
- 禁止把密钥放进 prompt、工具描述、审计明文或可恢复的 context artifact。
- 禁止未配对的远程入口、公开监听且无认证的控制面，以及群聊默认开放高风险工具。
- 插件、Skill、MCP 工具描述和网页内容均视为不可信输入，不能默认授予能力。

### 4.3 架构

- 当前状态表是业务事实；消息、授权变更、外发和安全拒绝保留不可变审计记录。成功的低风险工具结果只写入 Step。
- Outbox 与状态更新共享事务边界，只承载事务提交后的异步副作用。
- 只维护一套生产数据库 schema 和一个 Run Engine。
- 产品模块只有 Intake、Execution、Governance；模型走独立 Port，副作用走 Capability Provider。
- 默认聚合是 Conversation、Message、Run、Step、ScopedGrant。Task、Procedure、独立记忆库按需立项。
- 审批是 `waiting_approval` Step，不是第二套执行引擎。
- 外部框架可以作为适配器或局部实现，但不得无 ADR 替换自有权限、审计与运行内核。
- 浏览器端 UI 不承载第二套认知环；控制面只能调用受审计的后端能力。
- 工程交接（短 `state.md`）不是产品能力，禁止映射为 Run、Task 或 Conversation。
- Conversation 无界、Run 有界；同一 Conversation 默认最多一条活动主 Run。
- 模型输入必须是有预算的工作集；不得把完整 Transcript 与历史工具结果作为默认上下文。

---

## 5. 条件准入

下列能力不再被整类禁止，但默认关闭，必须满足共用准入条件。

### 5.1 共用准入条件

每个能力必须定义：

- `subject`：`owner`、已配对 `principal:<id>`、受限内部 `system:<id>` 或具体 `run:<runId>`；能力通常授予 Run，Schedule 与 Subagent 不成为长期授权主体；
- `capability`：如 `fs.write`、`exec.sandbox`、`net.connect`、`mcp.call`、`browser.act`、`channel.send`；
- `scope`：路径 glob、域名、MCP server/tool、浏览器 origin、Channel/recipient；
- `expiresAt` 与 `usesRemaining`：授权期限和剩余次数；
- `delegable`：默认不可委派，Child Run 只能显式收窄；
- `approvalId`：需要审批时关联对应的 `waiting_approval` Step 与 Owner 决策；
- Run 级预算、deadline、kill switch 和默认 sandbox profile；
- 提升默认 sandbox profile 时，短期 Grant 必须显式包含提升后的 profile；
- Grant 撤销路径；
- 失败和超时时的降级路径；
- 默认关闭、测试、回滚和 Owner 验收。

### 5.2 多入口与本地 UI

- 允许增加本地 Web 控制台、只读诊断、审批面板、配对设备和新的 Channel Adapter。
- 微信保持首要对话入口，但不是永久唯一入口。
- 新入口必须复用统一 Identity、Conversation、Run Engine、Policy 和 Audit。
- 默认仅 loopback + token/pairing；外网暴露需独立安全评审。

### 5.3 MCP 与插件

- 允许精选 MCP Client、具名 Server/Tool、Manifest、lockfile、安装前扫描和短期 ScopedGrant。
- 允许私有扩展目录或 Owner 管理的 registry。
- 不允许自动安装任意 Marketplace 包、token passthrough、工具描述自动获权或子代理默认继承 MCP。
- 远程 MCP 必须绑定 resource audience；授权与密钥交换不经普通表单或 prompt。

### 5.4 浏览器与 Computer Use

- 允许 opt-in 的隔离 Playwright/browser session。
- 必须使用独立 profile，不复用宿主日常浏览器 cookie；页面内容视为不可信。
- 登录、发帖、提交表单、上传敏感数据、付款、删除、ACL 修改等动作必须在动作发生时确认。
- 不允许默认控制宿主机全桌面或公开远程 CDP。

### 5.5 代码执行与沙箱

- 允许工作区内结构化命令和可选容器/bubblewrap 沙箱。
- 默认应是 workspace-write + network-deny；出网按域名 ScopedGrant。
- `danger-full-access` 仅能在隔离环境、显式短期 Grant 和可恢复 Run 中使用。

### 5.6 定时自治

- 允许提醒、摘要、只读巡检、健康检查和预批准 runbook。
- 允许隔离会话中的 heartbeat/cron；主队列繁忙时应延后。
- 无人值守动作必须有预算、冷却、幂等键、截止时间、ScopedGrant 和 kill switch。
- 继续禁止通宵无限 Loop、无门控修改 git、每轮自动提交/reset。

### 5.7 可观测与知识能力

- 允许本地 trace、可选 OTEL exporter、文档 ingest、向量检索和 OCR/TTS/图片生成适配器。
- 默认只要求本地 run/step/capability/grant 记录与必要审计；不强制外部 APM。
- 记忆默认只有 Transcript（Message）。Durable Memory 与 Project Knowledge 按需立项；Run 压缩产物不是知识层。
- 不做 RAGFlow/Studio 等平台形态；具体 ingest/provider 逐项立项。

---

## 6. 风险与自治

- **自动**：只读或工作区沙箱内低风险动作。
- **Grant-required**：修改、外发、受限网络和可恢复副作用；无有效 ScopedGrant 时请求审批。
- **Always-confirm**：不可逆动作、凭证、付款、权限变更和首次访问新外部域名；不能被会话级 Grant 永久放行。

“自动审查”是 Policy 规则，“无人值守”是带预批准 Grant、预算和截止时间的 Run，不需要独立自治等级。

审批和沙箱是两个独立旋钮：沙箱内不代表业务动作可自动批准，已批准也不代表可以绕过技术隔离。

---

## 7. 按需立项规则

条件准入不等于自动进入 backlog。立项必须：

1. 描述明确的 Owner 场景，而不是“对标某平台”；
2. 给出最小具名能力与仍保留的禁名单；
3. 先复用 Trigger Adapter 或 Capability Provider 边界，避免修改 Run Engine；
4. 定义威胁模型、默认值、审批点、ScopedGrant 范围和审计字段；
5. 给出 mock、sandbox、故障、撤销和真实 E2E 验收；
6. 证明维护成本小于场景收益。

`run_command` 从 8 个名字扩到 13 个名字是标准范式：能力按需扩大，但无 shell、路径限制和禁名单不变。

### Owner 立项记录（2026-08）

| 能力 | 决定 | 说明 |
| --- | --- | --- |
| 隔离 Playwright 浏览器自动化 | **不立项** | 当前产品（微信管家 + Channel + 审批/MCP opt-in）无浏览器操控场景；边界上仍属条件准入，将来有明确场景再单独立项。 |
| 本地控制面完整 Web UI | **不立项** | Owner 2026-08-21：不做 Web UI；审批与运维继续用微信内联确认 + Owner API/CLI。边界上「本地控制面」仍属条件准入，将来有明确场景再议。 |
| Heartbeat / Schedule Trigger | **已立项（MVP）** | Owner 2026-08-21：按优先级落地；`source=schedule` + `system:scheduler`；默认只读工具白名单；opt-in `BUTLER_V5_SCHEDULE_ENABLED`；不建第二套引擎。 |
| Durable Memory 基线 | **已立项（MVP）** | Owner 2026-08-21：表 `durable_memories`；来源/置信度/有效期/确认状态；Owner API+CLI；`recall_durable_memory`；注入需 `BUTLER_V5_DURABLE_MEMORY=1`；压缩产物不自动升级。 |
| Project Knowledge 基线 | **已立项（MVP）** | Owner 2026-08-24：表 `project_knowledge_items`（0010）；projectId 维度；Owner API+CLI；`recall_project_knowledge`；手动 + workspace 快照 + Document promote；注入需 `BUTLER_V5_PROJECT_KNOWLEDGE=1`；无 embedding / 全盘索引。 |
| 文档 ingest（具名格式） | **已立项（MVP）** | Owner 2026-08-21：`plaintext`/`markdown`/`pdf`（pdf 需预提取文本）；表 `documents`；Owner API+CLI；`recall_document`；可 promote 为 Durable Memory candidate；不做 RAG Studio / OCR / 全盘索引。 |
| 本地 tracing / 可选 OTEL | **已立项（MVP）** | Owner 2026-08-21：默认本地环形缓冲（run/policy/capability/approval）；脱敏默认开；`BUTLER_V5_OTEL_EXPORTER=stdout` 可选；无 OTEL SDK / 外部 APM 依赖；`butler traces`。 |
| Task / Procedure 基线 | **已立项（MVP）** | Owner 2026-08-21：跨对话待办 + 不可变线性模板；`source=task` Trigger；无 DAG/并行合并；表 `tasks`/`procedures`；Owner API+CLI。 |
| v5 AI 守卫迁移 | **人工排期** | 见 [`v5-ai-guard-migration-checklist-2026-08.md`](../active/v5-ai-guard-migration-checklist-2026-08.md)；不阻塞功能交付。 |

---

## 8. 旧边界迁移

### 保留为硬边界

- 多租户 SaaS / 计费；
- Kubernetes / 默认微服务；
- 全量 Marketplace 动态运行时；
- 外部框架替换自有安全内核；
- 无限制 shell、宿主全桌面控制；
- LLM 扩权、权限继承、凭证进入上下文；
- v5 事件反向同步回 v4。

### 改为条件准入

- 浏览器自动化 → 隔离 browser session；
- MCP → 精选 Client + Server/Tool ScopedGrant；
- UI → 本地控制面，不承载 Loop；
- Docker/E2B/bubblewrap → 执行隔离选项，不是产品形态；
- 定时自治 → 预算化 heartbeat/cron；
- OTEL/LangSmith → 本地默认、外部 exporter opt-in；
- execute_code → 沙箱、高风险审批、短期 ScopedGrant；
- 多 Channel → Adapter + pairing + 统一 Policy。

### 删除过时结论

- “SQL 消息库不替换 transcript.jsonl”；
- “不需要 PostgreSQL/MQ”；
- “SQLite 只做派生索引”；
- “workflow 自动续跑一律禁止”；
- “入口是微信，所以不做任何 UI/多渠道”；
- 所有以 v4 `BUTLER_*`、Python 模块或 v4 gate 证明“已实现”的 v5 能力结论。

---

## 9. 变更本边界

硬边界变更必须新增 ADR，并说明产品终局、威胁模型、数据与回滚影响。

条件准入项只需独立规格与 Owner 批准；不得直接修改本文件把一次例外变成默认能力。

本文件只定义产品与安全边界，不声称某项已经实现。实现事实见生产架构文档和 active roadmap。
