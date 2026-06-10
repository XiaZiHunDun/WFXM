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

## 厂长（Project Lead）决策

见 [project-lead-scope.md](./project-lead-scope.md)（五条能力、禁止项、阶段 1/2 清单）；平台 ADR 见 [`docs/architecture/project-lead-decision.md`](../../../docs/architecture/project-lead-decision.md)。

发版或克隆后同步项目 Skill（`.butler/skills` 不入 git）：

```bash
cd ~/projects/WFXM
bash scripts/sync-lingwen-project-skills.sh
bash scripts/butler-gateway-ops.sh restart   # 网关加载 Skill + Lead Loop
```

阶段 2：`/切换 灵文1号` 后会话使用 **项目 Lead** 引擎（非管家 Butler 主循环）；`/诊断` 可见「对话引擎: 项目 Lead」。

## 记忆试点

见 [memory-guide.md](./memory-guide.md)（写入对照表、`butler_remember` / `butler_recall`、`.env` 中的 `BUTLER_SYNC_CONVERSATION_MEMORY`）。

## 运营态双剧本

详见 **[dual-playbook.md](./dual-playbook.md)**（B1：维护态 / 新书态 + 微信验收句）。

`project.yaml` 中 `lifecycle: complete` 时走**维护态**；主公明确「新开一本」时走**新书态**（与 Skill `lingwen-project-lead` 一致）。

## 微信试点

**验收**：**2026-05-22 结论 — 通过，可运营。** 冒烟（0–8c）、记忆 M1–M4/M1b、Runtime、运维命令已复验；M-img/M-voice 暂缓。

| 文档 | 用途 |
|------|------|
| [`pilot-log.md`](./pilot-log.md) | 时间线与 §验收结论 |
| [`docs/guides/wechat-daily-smoke-checklist.md`](../../../docs/guides/wechat-daily-smoke-checklist.md) | 发版后真机检查表（**主清单**） |
| [`docs/guides/wechat-core-scenario.md`](../../../docs/guides/wechat-core-scenario.md) | 八步剧本详解 |

**说明**：验收步骤 4 会委派 content 写入 `docs/wechat-smoke.md`（运行时生成的验收文件），不是独立维护的手册；步骤定义见冒烟清单 §4 / 核心场景 §委派。

**自动化守门**：`bash scripts/butler-smoke.sh --tier=standard`（日常）或 `--tier=full`（发版）；灵文 Lead 见 `butler-lingwen-lead-smoke.sh`。

### 建议顺序（复测时）

1. `/状态` — 默认项目应为「灵文1号」（`BUTLER_DEFAULT_PROJECT`）
2. `读取 novel-factory/README.md 前 30 行并摘要`
3. `读取 workflow_state.json，说明当前 phase/step`
4. 委派只读 `docs/reference-snapshot/小说工厂问题记录.md`
5. 在 `docs/pilot-log.md` 记录进度（避免误改 `08_已发布/`）
6. `/工作流 run novel-factory-status` — 只读流水线状态
7. 工厂脚本（可选）：`.env` 设 `BUTLER_ENABLE_TERMINAL=1` 与 `BUTLER_TERMINAL_ALLOWLIST_EXTRA=python3,bash`
