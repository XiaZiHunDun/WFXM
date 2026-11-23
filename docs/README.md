# Butler 文档索引

> 更新：**2026-11-19** | 主线：**Butler v5**（单 Owner、自托管、可扩展个人管家）
> **新会话**：[`../AGENTS.md`](../AGENTS.md) → [`../DESIGN.md`](../DESIGN.md) → [`architecture/wfxm-agent-runtime.html`](architecture/wfxm-agent-runtime.html) → [`architecture/v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md)
> **文档体系**：[`DOCUMENTATION.md`](DOCUMENTATION.md)（分层、维护规则、勿从对照报告抽待办）
>
> **与 [`DOCUMENTATION.md`](DOCUMENTATION.md) 的关系**：本文是**卡片**（「我要…」问答快速链接表）；DOCUMENTATION 是**手册**（分层 + 维护规则 + 索引结构 + 变更记录）。

## 新会话入口

| 文档 | 说明 |
|------|------|
| [`../AGENTS.md`](../AGENTS.md) | Agent 必读索引 + v5 事实规则 + 撞点流程 |
| [`../DESIGN.md`](../DESIGN.md) | **v5 目标架构 SSOT**：三模块、五实体、混合数据、ScopedGrant |
| [`architecture/wfxm-agent-runtime.html`](architecture/wfxm-agent-runtime.html) | **当前实现全景与第一阶段验收**：三层架构、分层测试 L1–L4 |
| [`architecture/v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md) | **当前生产事实**：调用链、包和数据现状 |
| [`PROGRESS.md`](PROGRESS.md) | **开发进度台账**：阶段目标、验收证据、遗留与下阶段入口 |

## 协调与交接

| 文档 | 说明 |
|------|------|
| [`plans/decisions/v5-engineering-handoff-2026-08.md`](plans/decisions/v5-engineering-handoff-2026-08.md) | **交接规约 SSOT**（工程治理，非产品运行时） |

## 快速入口

| 我要… | 读这里 |
|-------|--------|
| 改 v5 目标架构 | [`../DESIGN.md`](../DESIGN.md) |
| 改 v5 代码 / 查模块 | [`architecture/v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md) + [`../AGENTS.md`](../AGENTS.md) |
| 查 v5 环境变量 | [`ENV.md`](ENV.md) · [`../.env.example`](../.env.example) |
| 配置放哪（env/yaml/secrets） | [`ENV.md`](ENV.md) · [`templates/permissions.yaml.example`](templates/permissions.yaml.example) |
| 权限门控 / 扩展接缝 | [`../DESIGN.md`](../DESIGN.md) §10 / §7.1 |
| **v5 功能清单 / 已 ship** | [`FEATURES.md`](FEATURES.md) |
| **v5 API endpoint** | [`API_ENDPOINTS.md`](API_ENDPOINTS.md) |
| **v5 测试覆盖** | [`TESTS.md`](TESTS.md) |
| **v5 TODO / deferral** | [`TODO_DEFERRED.md`](TODO_DEFERRED.md) |
| **D-series audit findings** | [`AUDIT_FINDINGS.md`](AUDIT_FINDINGS.md) |
| **Feedback lessons** | [`FEEDBACK.md`](FEEDBACK.md) |
| **工程治理一页纸** | [`GOVERNANCE.md`](GOVERNANCE.md) |
| **发版 / 生产加固** | [`deployment/production-hardening.md`](deployment/production-hardening.md) |
| 看规划与命名 | [`plans/README.md`](plans/README.md) |
| **v5 产品边界 / 条件准入** | [`plans/decisions/v5-product-boundaries-2026-08.md`](plans/decisions/v5-product-boundaries-2026-08.md) |
| **v5 后续路线** | [`plans/active/v5-post-boundary-roadmap-2026-08.md`](plans/active/v5-post-boundary-roadmap-2026-08.md) · [`ROADMAP.md`](ROADMAP.md) |
| **v5 owner FAQ** | [`FAQ.md`](FAQ.md) |
| 目录与命令 | [`../STRUCTURE.md`](../STRUCTURE.md) |

## 架构与设计

| 文档 | 说明 |
|------|------|
| [`../DESIGN.md`](../DESIGN.md) | v5 目标架构 SSOT |
| [`architecture/wfxm-agent-runtime.html`](architecture/wfxm-agent-runtime.html) | 当前实现全景、L1–L4 分层测试与达标判定 |
| [`architecture/v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md) | 当前生产调用链与包边界 |
| [`architecture/v5-current-state-diagrams.md`](architecture/v5-current-state-diagrams.md) | 视觉架构图（Mermaid 4 张） |
| [`architecture/v5-r10-handoff.md`](architecture/v5-r10-handoff.md) | v5 迁移交接与保护层 |
| [`architecture/v5-r12-verification-2026-08.md`](architecture/v5-r12-verification-2026-08.md) | v5 R12 验证记录 |
| [`adr/2026-08-08-v4-to-v5-supersession.md`](adr/2026-08-08-v4-to-v5-supersession.md) | v4 → v5 取代决策 |
| [`adr/effects-integration.md`](adr/effects-integration.md) | Effect-TS 集成决策 |

## 运维与部署

| 文档 | 说明 |
|------|------|
| [`deployment/README.md`](deployment/README.md) | 部署文档索引 |
| [`deployment/SELF-HOSTING.md`](deployment/SELF-HOSTING.md) | 自托管完整指南（§0–§10） |
| [`deployment/production-hardening.md`](deployment/production-hardening.md) | 生产加固清单 |
| [`ENV.md`](ENV.md) | v5 `BUTLER_V5_*` 环境变量总表 |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | 安装、测试分层、AI Guard、提交规范 |

## 规划与评估

| 文档 | 说明 |
|------|------|
| [`DOCUMENTATION.md`](DOCUMENTATION.md) | 文档分层 L0–L4 与维护规则 |
| [`plans/README.md`](plans/README.md) | 规划索引 |
| [`ROADMAP.md`](ROADMAP.md) | D-series 累计与后续候选 |
| [`FAQ.md`](FAQ.md) | owner 视角 FAQ |
| [`plans/decisions/v5-product-boundaries-2026-08.md`](plans/decisions/v5-product-boundaries-2026-08.md) | v5 需求 / 边界决策入口 |
| [`plans/active/v5-post-boundary-roadmap-2026-08.md`](plans/active/v5-post-boundary-roadmap-2026-08.md) | v5 P0–P4 后续路线 |
| [`plans/decisions/v5-engineering-handoff-2026-08.md`](plans/decisions/v5-engineering-handoff-2026-08.md) | 工程交接规约 |

## 配置模板

| 文档 | 说明 |
|------|------|
| [`ENV.md`](ENV.md) | `BUTLER_V5_*` 速查 |
| [`templates/README.md`](templates/README.md) | 模板集合索引 |
| [`templates/permissions.yaml.example`](templates/permissions.yaml.example) | 项目 `.butler` 配置目录下的 `permissions.yaml` 模板 |

## 子目录速查

> 导航中心（仅索引，不重复内容）。详细分层与维护规则 → [`DOCUMENTATION.md`](DOCUMENTATION.md)

| 子目录 | 权威指南 | 何时来这 |
|--------|----------|----------|
| `architecture/` | [`v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md) | 查生产调用链 / 视觉架构图 / 实现全景 |
| `adr/` | [`2026-08-08-v4-to-v5-supersession.md`](adr/2026-08-08-v4-to-v5-supersession.md) | 查架构决策记录 |
| `deployment/` | [`SELF-HOSTING.md`](deployment/SELF-HOSTING.md) · [`production-hardening.md`](deployment/production-hardening.md) | 自托管与生产加固 |
| `plans/` | [`v5-post-boundary-roadmap-2026-08.md`](plans/active/v5-post-boundary-roadmap-2026-08.md) | 决策 / 路线 |
| `templates/` | [`README.md`](templates/README.md) | 模板集合 |

## 验证命令

```bash

pnpm typecheck
pnpm lint
pnpm test
pnpm test:acceptance
npx tsx scripts/l4-smoke.ts

# L4 可靠性
npx tsx scripts/l4-smoke.ts --suite reliability
```

L4 需要网关已启动，并从 `~/.config/env` 读取 `BUTLER_V5_INBOUND_SHARED_SECRET`。
