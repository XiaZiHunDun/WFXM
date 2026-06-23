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
- ~~`tests/` 域化（新测进子目录，旧 sprint 保留）~~ **2026-06-23 已完成**（gateway/ops/dev_engine + `butler-domain-pytest.sh` + CI `domain-gates`）
- ~~`dev-cc-head-to-head.md` 与 verify 状态同步~~ **2026-06-23 已完成**
