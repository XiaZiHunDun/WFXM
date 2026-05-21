# 灵文1号 · WFXM 试点说明

## 命名

| 名称 | 含义 |
|------|------|
| **灵文1号** | Butler 项目名（`project.yaml` 的 `name`，微信 `/切换 灵文1号`） |
| **正式灵文** | 线上/历史生产项目，与本仓库 **无同步关系** |
| `projects/LingWen1/` | 本仓库内唯一可写工作区目录名 |

## 路径角色

| 路径 | 角色 |
|------|------|
| `reference/AI-Incursion/.../LingWen/` | 只读参考标本（勿改、勿软链写入） |
| `projects/LingWen1/` | Butler 试点工作区（微信 / 工具只碰这里） |

## 工作副本（B1）

- **来源**：`reference/.../novel-factory/` 一次性全量复制（2026-05-21）
- **落盘**：`projects/LingWen1/novel-factory/`（约 17MB，《星陨纪元》完结态快照 + 工具脚本）
- **参考文档**：`docs/reference-snapshot/`（问题记录、工作室方案）

之后所有读写、委派、脚本执行只落在 `projects/LingWen1/` 下。

## 从 reference 再同步（可选，人工、向下）

```bash
SRC="$HOME/projects/WFXM/reference/AI-Incursion/domains/IP创作/projects/LingWen/novel-factory"
DST="$HOME/projects/WFXM/projects/LingWen1/novel-factory"
rsync -a --delete "$SRC/" "$DST/"
```

不要从 `projects/` 回写 `reference/`。

## 记忆试点

见 [memory-guide.md](./memory-guide.md)（写入对照表、`butler_remember` / `butler_recall`、`.env` 中的 `BUTLER_SYNC_CONVERSATION_MEMORY`）。

## 微信试点（建议顺序）

1. `/状态` — 默认项目应为「灵文1号」（`BUTLER_DEFAULT_PROJECT`）
2. `读取 novel-factory/README.md 前 30 行并摘要`
3. `读取 workflow_state.json，说明当前 phase/step`
4. 委派只读 `docs/reference-snapshot/小说工厂问题记录.md`
5. 在 `docs/pilot-log.md` 记录进度（避免误改 `08_已发布/`）
6. `/工作流 run novel-factory-status` — 只读流水线状态
7. 工厂脚本（可选）：`.env` 设 `BUTLER_ENABLE_TERMINAL=1` 与 `BUTLER_TERMINAL_ALLOWLIST_EXTRA=python3,bash`
