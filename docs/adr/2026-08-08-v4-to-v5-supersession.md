# ADR-0001: Butler v4 → v5 全面替代

- Status: Accepted + v4 DECOMMISSIONED
- Date: 2026-08-08 (Accepted) / 2026-08-16 (v4 Decommissioned)
- Deciders: 项目 Owner
- Supersedes: 此前未成文的"持续深化 v4"默认口径（参见 Context 与已批准规格 §1）

## Status Update — v4 Decommissioned (2026-08-16)

2026-08-16 标记 v4 runtime 全面退役（v4 cutover 已于 2026-08-14 完成 standby），所有 v4 systemd 服务 / timer 已停用，v4 数据保留为历史参考。

### v4 systemd services — stopped + disabled (2026-08-16)

| Unit | Action |
| --- | --- |
| `butler-gateway.service` | stopped + disabled (also detached symlink in `default.target.wants`) |
| `butler-runtime-lingwen.service` | stopped + disabled |
| `butler-morning-brief.service` | stopped + disabled |
| `butler-push-drain.service` | stopped + disabled |
| `butler-b9-weekly-gate.service` | stopped + disabled |
| `butler-eval-sync.service` | stopped + disabled |
| `butler-ops-cadence-weekly.service` | stopped + disabled |
| `butler-ops-cadence-quarterly.service` | stopped + disabled |

### v4 systemd timers — stopped + disabled (2026-08-16)

为防止已禁用 service 被 timer 重新触发，关联的 `.timer` 单元同步停用：

- `butler-runtime-lingwen.timer`
- `butler-morning-brief.timer`
- `butler-push-drain.timer`
- `butler-b9-weekly-gate.timer`
- `butler-eval-sync.timer`
- `butler-ops-cadence-weekly.timer`
- `butler-ops-cadence-quarterly.timer`

（`butler-gateway.service` 无对应 timer，原 v4 主进程通过 `pkill` 同步清理；其余 stray Python 进程均已 kill。）

### v4 资产保留口径

- **v4 代码（`butler/` 目录）**：保留为历史参考，不删除。ADR-0001 仍视 v4 为已批准规格下的 legacy runtime，仅归档读取，不作为产品主线。
- **v4 用户数据（`~/.butler/`）**：保留。包含 `state.md`、`memory/`、`coding_experiences.json`、`butler.db`、`blackboard/`、`gateway/`、`exports/` 等历史产物；用户可按需离线查询或后续手动归档。
- **v5 单元（`butler-v5-gateway.service`）**：继续 active running，为唯一对外入口。
- **回滚路径**：v4 仅在 v5 出现 P0 不可恢复故障时作为应急恢复路径启用，需新 ADR 重新激活。

### R10.x Decommission 实施记录

- Shift card：`.blackboard/shifts/2026-08-16-claude-code-027.md`
- 实施日期：2026-08-16
- Owner 后续可选动作：决定是否在观察期后删除 `~/.butler/` 历史数据；建议保留至少 30 天作为可恢复期。

## Context

WFXM 当前同时承载 Butler v4 Python 产品主线和 Butler v5 TypeScript 原型，双轨状态已经成为交付与治理风险，而不是可持续的兼容策略。根据 [`docs/analysis/project-status-2026-08-08.md`](../analysis/project-status-2026-08-08.md)：

- v4 的 `butler/` 已达到 **1,490 个 Python 文件、196,873 行**，具备微信、CLI、Agent Loop、委派、记忆、权限、运维与评估等完整产品能力；
- Effects、Event、Tool Registry、Skill、Budget、Guard 等多个架构深化方向仍处于未集成或未形成可发布边界的 WIP，当前工作区同时存在大量 v4 modified 文件和未跟踪实验资产；
- `butler-v5/` 已用 TypeScript + Effect-TS 验证 Functional Core / Imperative Shell、CQRS、Event Sourcing 与 Guard 等方向，但整目录仍是独立原型，尚未纳入 v4 主树运行时引用，也不是已发布主线；
- v4 的继续深化与 v5 原型并行，导致设计、测试、发布、数据和运维责任重复，双轨管理开销持续放大；当前工作区不是可以直接发布的单一产品状态。

已批准的 [`docs/superpowers/specs/2026-08-08-wfxm-rearchitecture-design.md`](../superpowers/specs/2026-08-08-wfxm-rearchitecture-design.md) 已确认终局为 Butler v5 全面替代 v4；v4 仅作为迁移期 legacy runtime，切换后只读归档；允许命令、配置和 API 的破坏性升级；部署目标为单机自托管的 Docker Compose；核心范式为 Functional Core / Imperative Shell、ADT、Effect、CQRS 与 Event Sourcing；主存储采用 PostgreSQL Event Store、Projection、Outbox 与 pgvector；迁移采用 Strangler + Shadow + Cutover，而不是大爆炸重写。

因此，需要一份正式 ADR 结束“继续深化 v4”与“迁移 v5”之间的未决状态，明确唯一产品主线、v4 的维护边界、v5 的部署和数据迁移责任，以及可执行的回滚口径。

## Decision

- **Butler v5 是唯一活动产品主线。** 新产品能力、架构投资、主线测试和发布门禁均以 v5 为准。
- **Butler v4 进入 maintenance。** v4 仅接受 P0 安全修复和 P0 生产修复，不再作为新能力的研发主线。
- **允许破坏性升级。** 不复刻 v4 的命令、配置和 API 表面；v5 以新的领域、Application、Runtime、Port 和 Adapter 边界提供产品能力。
- **部署目标为单机自托管 + Docker Compose。** 首个生产切片不以多租户 SaaS、Kubernetes 或网络微服务拆分为目标。
- **数据迁移以核心资产为范围。** 迁移项目、记忆、任务、审批、Skill 元数据和经验；旧会话与派生索引不作为在线兼容数据迁移，采取离线归档或重建。
- **v5 采用模块化单体和事件驱动内核。** Domain、Application、Runtime、Ports、Adapters、Projections 和 Apps 通过强边界协作，Event Store 作为事实源，Projection 作为可重建读模型。
- **迁移采用 Strangler + Shadow + Cutover。** 先建立可验证的 v5 垂直切片和资产导入，进行影子运行与差异校验，再按明确门禁切换流量，不采用一次性大爆炸重写。
- **回滚以切换前 v4 快照为边界。** 回滚恢复切换前保存的 v4 运行快照；不把 v5 事件反向迁移为 v4 状态，也不承诺双向实时同步。

## Consequences

### 正面影响

- 产品、架构、测试、文档和发布决策只有一条活动主线，停止为 v4 与 v5 同时维护完整演进路线。
- v5 可以直接落实已批准的 FC/IS、ADT、Effect、CQRS、Event Sourcing、Port/Contract 和 Guard 设计，不再被 v4 兼容表面牵制。
- PostgreSQL Event Store、Projection、Outbox、审计、备份和恢复成为统一的生产数据与运维边界。
- 迁移范围聚焦项目、记忆、任务、审批、Skill 元数据和经验等可复用核心资产，避免把 v4 的全部历史文件和派生索引机械搬运到 v5。

### 代价与约束

- v4 的新功能请求、架构级抽象和非 P0 缺陷将被拒绝、延期或转化为 v5 需求；v4 不再增加新的架构级抽象。
- 现有 v4 命令、配置和 API 不保证兼容，用户和集成方需要接受新的 v5 交互、配置及 API 合同。
- 切换期间必须同时承担 v4 维护、v5 构建、影子运行、数据校验和快照管理的短期成本；只有切换完成后才能逐步关闭 v4 运行职责。
- 旧会话和派生索引可能只能离线查询或通过 v5 重建，迁移工具必须明确报告跳过项、损失项和校验结果。
- 回滚窗口依赖切换前 v4 快照的完整性、可恢复性和保留期限；v5 切换后的新事件不会自动回写 v4，因此回滚可能丢失切换后产生的 v5 状态变化。
- 在 v5 完成 Cutover 前，v4 仍作为迁移期 legacy runtime 承载生产流量；该运行事实不构成 v4 与 v5 的平行产品承诺，治理与发布口径仍以 v5 为唯一活动主线。

## Migration Plan Reference

- R0–R7 阶段定义见 [`docs/superpowers/specs/2026-08-08-wfxm-rearchitecture-design.md`](../superpowers/specs/2026-08-08-wfxm-rearchitecture-design.md)。
- 实施计划见 [`docs/superpowers/plans/2026-08-08-wfxm-v5-replacement-implementation-plan.md`](../superpowers/plans/2026-08-08-wfxm-v5-replacement-implementation-plan.md)。

本 ADR 只确定终局和边界；各阶段的入口条件、证据门禁、Owner 复核、快照保留、迁移校验和 Cutover/回滚操作以批准规格与实施计划为准。任何偏离本决策的兼容性承诺或重新启用 v4 作为产品主线的变更，都必须提交新的 ADR。
