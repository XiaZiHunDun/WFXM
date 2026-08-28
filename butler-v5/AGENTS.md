# Butler v5 — Agent 工作说明（TypeScript + Effect-TS）

> 本文档是 AI 编码工具（Cursor / Claude Code / Trae / Copilot 等）在 Butler v5 项目中的**行为契约**。
> 所有 Agent 必须在每次会话开始时加载本文档，并严格遵守所有规则。
> 设计参考：[`DESIGN.md`](DESIGN.md)

---
## 0. 三层事实（生产 vs 脚手架）

| 层 | 文档/代码 | Agent 怎么用 |
| --- | --- | --- |
| **生产** | `docs/architecture/v5-production-architecture-2026-08.md` + `apps/api` + `packages/runtime` + `packages/persistence` | 改功能、查调用链 |
| **脚手架（未接线）** | `_archive/packages/application/`、`_archive/packages/infrastructure/` | 不要当已实现；不要用其单测声称能力已交付 |
| **目标架构** | `DESIGN.md`、Policy/ScopedGrant/Sandbox | 规划用，不等于生产已有 |

**修改 butler-v5/ 后必跑：** `cd butler-v5 && pnpm test`（默认不含 `_archive` 脚手架测试；需时用 `pnpm test:archived`）

> §一 的包表按六边形三条带（Core / Ports / 适配器）组织，描述的是**目标架构**；生产 delivery shell 为 async/await + RunEngine，见生产架构文档。

> **运行时安全 vs 开发守卫**：生产路径用 `PolicyGate` + `ScopedGrant` + `waiting_approval` + Owner loopback API（见 production architecture）。§十 GUARD、`load-bearing-marks.json` 与 `_archive/packages/infrastructure/_archive/guards/` 是**开发 Butler 仓库时的 AI/工程守卫**，不在微信主路径 runtime 执行。

---


## 一、项目概述

Butler v5 是微信编码管家的**模块化单体**，采用 TypeScript，目标架构为**六边形（端口-适配器）**：内核 Domain→Application→Ports 单向分层，Driving/Driven 适配器走两条接缝。生产 delivery shell 为 async/await + RunEngine（见生产架构文档）。Effect-TS 是可选实现工具，只在生命周期/并发/cancel 语义处使用。目标架构见 [`DESIGN.md`](DESIGN.md) §1–§17。

| 包带 | 包 | 职责 | 依赖方向 |
| --- | --- | --- | --- |
| Core 内核 | `runtime` | Application 编排（RunEngine / PolicyGate / 审批 / working-set） | → ports + domain |
| Core 内核 | `domain` | 纯规则 / 聚合 / 状态机（零依赖） | 不 import 任何项目包 |
| Ports | `ports` | 端口接口定义（Repository / Model / Capability / Channel / Clock） | 只依赖 domain 类型 |
| Driven 适配器 | `persistence` | 唯一 schema + repo（runtime-store / event-store / outbox） | → ports + domain |
| Driven 适配器 | `adapters` | LLM / Channel / 沙箱 / MCP | → ports + domain + 协议 SDK |
| Driving 适配器 | `apps/*`、`cli` | HTTP / WS / CLI 入口 + Composition Root（wiring） | → Core.Ports → Core |
| 配置/共享（可选瘦身） | `config`、`shared` | 精简后的零依赖纯工具 | 零项目依赖 |

> `_archive/packages/application`、`_archive/packages/infrastructure` 是**未接线脚手架**（根 `_archive/`），不在生产调用链；不要用其单测声称能力已交付。

## 二、核心行为准则（七级决策阶梯）

在生成任何代码之前，依次检查以下阶梯，在第一个满足的阶梯停下：

```
1. YAGNI        — 这个需求真的需要实现吗？
2. 代码库复用    — 是否已有类似实现？（先 grep 搜索）
3. 标准库       — TypeScript/Node.js 标准库是否已提供？
4. 原生平台     — Effect-TS 是否已内置此能力？
5. 已安装依赖   — 已安装的依赖是否能解决？
6. 一行代码     — 能否用一行代码解决？
7. 最小实现     — 最后才写最小可用代码
```

**防过度工程**：不做调用链深度限制、不做类型/函数预算硬性限制。用 `ts-prune`（CI 死代码检测）+ 文件大小门禁（>800 警告，>1200 阻止）替代。

## 三、安全边界（永不能偷懒的事项）

- 理解问题（必须完整阅读并追踪真实流程）
- 信任边界处的输入验证
- 防止数据丢失的错误处理
- 生产运行时：`PolicyGate` / ScopedGrant / 审批 Step / Audit（见 production architecture）
- 开发仓库：scope-boundaries、pre-tool hooks、§十 GUARD（不混入产品运行时）
- 用户的明确要求

## 四、关键文件（review 后可改；不再 block）

**R17 (2026-08-28) 退役 v5 AI guard hook**（DESIGN §19 工程治理 ≠ 目标架构）后，原"BLOCK：绝不允许 AI 直接修改"链路已移除。下表文件**仍需人工 review**，但不再被强制 block —— AI 工具可改，commit review + 5 gate + architecture tests 兜底。

| 文件                              | 风险                                   |
| --------------------------------- | -------------------------------------- |
| `packages/domain/src/errors.ts`   | 全局错误 ADT，contract test 兜底       |
| `packages/ports/src/index.ts`     | Effect Tag 接口（thin barrel），package-membership.test 兜底 |
| `.cursorrules`                    | AI 行为规则，由 .blackboard/state.md 不要做段兜底 |
| `AGENTS.md`                       | 本文件，由 .blackboard/state.md 顶部班段兜底 |

承重文件保护历史 ADR：`docs/adr/2026-08-08-hook-path-fix-manual-override.md`（R17 退役前最后修复）。
| `.butler/scope-boundaries.json`   | 安全边界配置                           |
| `.butler/load-bearing-marks.json` | 承重代码标记                           |

## 五、工程约束

| 约束        | 阈值                  | 行为                       |
| ----------- | --------------------- | -------------------------- |
| 单文件行数  | >800                  | 警告（建议拆分）           |
| 单文件行数  | >1200                 | 阻止（必须拆分）           |
| 跨层 import | Core（runtime/domain）→ 具体适配器（persistence/adapters 实现） | 阻止（违反端口化/依赖方向） |
| 危险模式    | `import *`            | 阻止                       |
| 全局副作用  | 模块级 `new Map()`    | 警告（应放 Layer 内）      |
| 死代码      | 未使用的导出          | 警告（`ts-prune` CI 检查） |

## 六、Scope 边界（四栏表）

遵循 `.butler/scope-boundaries.json` 定义的四栏边界：

- **reads**：可读范围
- **writes**：可写范围（reads 的子集）
- **executes**：可执行命令（白名单）
- **off_limits**：绝对禁区（优先级最高）

## 七、代码规范

### 类型定义

- 所有 union 类型用 `_tag` 区分
- 所有字段 `readonly`
- 禁止 `optional + null`，用 `Option<T>` 或可辨识 union

### 错误处理

- 禁止 `throw`，用 `Effect.fail` 或 `Either`
- 所有可恢复错误走 `LoopError` ADT

### 测试

- 领域层：纯函数单元测试，零 mock
- 应用层：Mock Layer 注入，测试 Effect 编排
- 基础设施层：真实 Layer 集成测试
- 守卫测试：架构约束验证
- 契约测试：Port 接口稳定性

### 注释

- 纯函数：用 `// ─── 标题 ──` 分隔段落
- 副作用函数：用 `// [G-N]` 标注对应 GUARD

## 八、提交规范

- 提交前运行 `pnpm typecheck && pnpm test`
- 受保护文件修改必须包含 `[MANUAL-OVERRIDE]` 标记
- 不要在提交中包含 `.env` 或 credentials

## 九、反模式清单（已记录，勿重蹈覆辙）

见 `.butler/anti-patterns/registry.json`。每次迭代前自动加载。

## 十、7 条 GUARD 机制速查（开发仓库用，非生产 runtime）

> 实现位于 `_archive/packages/infrastructure/_archive/guards/`；**未接入** `apps/api` / `packages/runtime` 微信主路径。产品运行时审批见 `PolicyGate` + Owner API。

| #       | 机制           | 触发条件                                 |
| ------- | -------------- | ---------------------------------------- |
| **G-1** | 证据门控       | 每次写操作必须留存 IntentReceipt         |
| **G-2** | 承重防护       | 修改 load-bearing 标记文件需 Owner 签名  |
| **G-3** | Owner 离线策略 | 离线时 write/execute 拒绝，delegate 入队 |
| **G-4** | 签名验证       | 承重代码修改需 Owner HMAC 签名           |
| **G-5** | 多文件链路     | 修改主文件时检查关联文件是否同步         |
| **G-6** | 角色分离       | Author ≠ Reviewer                        |
| **G-7** | 3 层自愈       | Retry → Fallback → OwnerNotify           |

> 原 G-9（反模式归档）、G-10（混沌演练）降级为预留功能，不在核心 GUARD 中。

## 十一、结构化信息维护原则

**人类不直接维护结构化文件**。以下文件由 AI 工具根据人类自然语言意图自动生成，人类仅通过可视化反馈确认：

| 文件                                  | 用途         | 维护方式               |
| ------------------------------------- | ------------ | ---------------------- |
| `DESIGN.md`                           | 架构设计规范 | AI 生成 + 人类确认     |
| `AGENTS.md`                           | AI 行为契约  | AI 生成 + 人类确认     |
| `.cursorrules`                        | 代码规则     | AI 生成 + 人类确认     |
| `.butler/scope-boundaries.json`       | 安全边界     | AI 生成 + 人类确认     |
| `.butler/load-bearing-marks.json`     | 承重代码     | AI 生成 + 人类确认     |
| `.butler/anti-patterns/registry.json` | 反模式注册   | 自动记录（Owner 触发） |

**工作流**：人类意图 → AI 生成结构化信息 → AI 生成可视化 → 人类确认 → 写入文件
