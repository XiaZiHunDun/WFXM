# Butler Docs — 文档目录

> **层级**：文档 / 知识  
> **父文档**：[`../AGENTS.md`](../AGENTS.md)  
> **架构参考**：[`v4-architecture.md`](architecture/v4-architecture.md) §7

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
| `architecture/` | 架构文档 | 九层模型、分层理论、工程映射 |
| `guides/` | 操作指南 | 部署配置、维护手册、发版手册 |
| `plans/` | 规划文档 | 路线图、决策记录、差距登记 |
| `config/` | 配置参考 | `BUTLER_*` 环境变量参考 |

## 必读文档（按顺序）

| # | 文档 | 何时读 |
|---|------|--------|
| 1 | `architecture/v4-architecture.md` | 改 Loop / Gateway / 模块 / 分层选型 |
| 2 | `guides/deploy-profiles-2026-06.md` | 上手配置 |
| 3 | `plans/decisions/roadmap-backlog-and-boundaries-2026-05.md` | 提需求 / 否决 / Backlog |
| 4 | `DOCUMENTATION.md` | 文档分层、语料、规划索引 |
| 5 | `plans/decisions/theory-implementation-gap-register-2026-06.md` | 理论—实现差距 |

## 注意事项

1. **文档同步**：改 CC 线束、外部对标模块、ENG-15 层矩阵或新增 `BUTLER_*` 时，同步 `v4-architecture`、`v4-layer-model`、`config/reference`、`.env.example`
2. **历史文档**：`docs/history/` 和 `docs/plans/comparisons/*` 正文旧 P0/P2 表**非待办**，勿作实现依据
3. **文档维护**：参考 `DOCUMENTATION.md` §6 的维护规则

## 相关目录

- 根文档：[`../AGENTS.md`](../AGENTS.md)
