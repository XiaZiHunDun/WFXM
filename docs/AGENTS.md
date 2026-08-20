# Butler Docs — 文档目录

> **层级**：文档 / 知识  
> **父文档**：[`../AGENTS.md`](../AGENTS.md)  
> **目标架构**：[`../butler-v5/DESIGN.md`](../butler-v5/DESIGN.md)
> **当前事实**：[`v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md)

## 目录结构

```
docs/
├── README.md                      # 文档索引
├── architecture/                  # 架构文档
├── guides/                        # 操作指南
├── plans/                         # 规划文档
├── config/                        # 配置参考
├── DOCUMENTATION.md               # 文档体系说明
└── （其他子目录）
```

## 子目录说明

| 子目录 | 职责 | 说明 |
|--------|------|------|
| `architecture/` | 架构文档 | v5 生产事实、handoff、ADR；目标架构在 `butler-v5/DESIGN.md` |
| `guides/` | 操作指南 | 部署配置、维护手册、发版手册（注意 v4/v5 状态） |
| `plans/` | 规划文档 | 路线图、决策记录、差距登记 |
| `config/` | 配置参考 | 主要为 v4 历史；v5 先查 `butler-v5/.env.example` |

## 必读文档（按顺序）

| # | 文档 | 何时读 |
|---|------|--------|
| 1 | `../butler-v5/DESIGN.md` | 改目标架构、概念、安全、数据或扩展边界 |
| 2 | `architecture/v5-production-architecture-2026-08.md` | 查当前生产 Loop / Gateway / 数据 / 模块 |
| 3 | `plans/decisions/v5-product-boundaries-2026-08.md` | 提需求 / 条件准入 / 否决 |
| 4 | `plans/active/v5-post-boundary-roadmap-2026-08.md` | 后续优先级 |
| 5 | `DOCUMENTATION.md` | 文档分层、语料、规划索引 |
| 6 | `architecture/v5-r10-handoff.md` | 部署与历史交接 |

## 注意事项

1. **文档同步**：改目标架构先更新 `butler-v5/DESIGN.md`；改当前生产调用链再更新 production architecture。Policy/ScopedGrant、数据边界或扩展接缝变化还需同步 product boundaries 与 roadmap。工程交接变化同步 `v5-engineering-handoff-2026-08.md` 与 `AGENTS.md`，不要把黑板写进产品状态机。
2. **历史文档**：v4 architecture、`docs/history/` 和 `docs/plans/comparisons/*` 正文旧表**非 v5 待办**，勿作实现依据
3. **文档维护**：参考 `DOCUMENTATION.md` §6 的维护规则

## 相关目录

- 根文档：[`../AGENTS.md`](../AGENTS.md)
