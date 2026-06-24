# 仓库整理审计快照（2026-06-23）

> 阶段 0 只读摸底 + 阶段 1 文档/工作区卫生执行记录。

## 阶段 0 基线

| 检查 | 结果 |
|------|------|
| `project-health-check.sh quick` | **OK**（143 + 114 pytest） |
| `repo-cleanup-audit.sh` | 报告 `logs/maintenance/repo-cleanup-20260623-172239.md` |
| `docs-lint.sh` | **7 条断链**（多为 history / extension 相对路径；非本次阻塞） |

## 阶段 1 已执行

| 项 | 动作 |
|----|------|
| 根目录游离 plan | → `docs/plans/archive/butler-closed-loop-optimization-plan-2026-06-09.md` |
| `docs/superpowers/` | → `docs/plans/archive/superpowers/` |
| Dev 飞轮调试 md | → `docs/archive/dev-flywheel/` |
| `STRUCTURE.md` | 同步 `butler/project/`、`dev_engine/`、`ops/` |
| `scripts/README.md` | 增补 eval/B9/sim/head-to-head/ops 索引 |
| `.gitignore` | `coverage.json`、`.mypy_cache/` |

## 待后续（阶段 2+）

- ~~Gateway 命令单轨（`gateway/` 根 → `gateway/commands/`）~~ **2026-06-23 已完成**（handlers 迁入 `commands/*_handlers.py`，删除根级 `*_commands.py`）
- ~~`tests/` 域化（新测进子目录，旧 sprint 保留）~~ **2026-06-23 已完成**（gateway 547 passed；CI `domain-gates` gateway/ops/memory/core 已绿）
- ~~`dev-cc-head-to-head.md` 与 verify 状态同步~~ **2026-06-23 已完成**

## CI 状态（2026-06-24）

| Job | 状态 | 备注 |
|-----|------|------|
| lint / corpus-drift / smoke | ✅ | `11ccd1f` 起 |
| domain-gates gateway/ops/memory/dev_engine/core | ✅ | `b44d062` 起 |
| docs-lint | ✅ | 跳过 gitignore 的 pilot-log / reference / history 链 |
| pytest + coverage | 🔧 | 压缩 mock、fastembed skip、skill 注入 patch（`b44d062` 后） |

## 阶段 3（待办）

- 旧 sprint 测迁入域目录或标记 legacy
- `reference.md` ↔ `.env.example` 数量对齐（505/497，差 8 为注释项）
- `post-consolidation-roadmap` 测试基线数字更新
