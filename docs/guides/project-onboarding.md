# Butler 项目接入指南

> 用户、管家、项目协作模型见 [`architecture/project-layer-wechat-plan.md`](../architecture/project-layer-wechat-plan.md) §2–§4。  
> 本文是运维/开发按表执行的**接入清单**。

---

## 1. 接入前提

| 项 | 要求 |
|----|------|
| 位置 | 目录在 `BUTLER_PROJECTS_DIR` 下（默认仓库 `projects/`） |
| 安全根 | 建议在 `BUTLER_TOOL_SAFE_ROOT` 内，否则 Agent 工具可能拒访 |
| 登记文件 | `project.yaml`（`name` 为微信 `/切换` 用的**显示名**） |
| 工作区 | 实际 workspace = `project.yaml` **所在目录** |

---

## 2. 三条路径

### A. Butler 新建（空项目）

```bash
butler create MySlug --type software --description "说明"
butler project preflight --path projects/MySlug
butler memory-reindex --project "MySlug"   # 若 name 与目录名不同，用 project.yaml 的 name
```

模板也可从 [`docs/templates/project-archetypes/`](../templates/project-archetypes/) 复制后改 `name`。

### B. 拷贝 / 迁入（如灵文1号）

1. 将完整树放入 `projects/<ASCII目录>/`（勿写入 `reference/` 只读区）。
2. 编写或合并 `project.yaml`（参考 `novel-factory.project.yaml` 模板）。
3. 补 `docs/pilot-setup.md`（路径角色、禁止项、微信验收顺序）。
4. 若启用厂长：`BUTLER_LEAD_PROJECTS` 加入 `name`，并放置 `skills/*-project-lead.md`。
5. 可选 `runtime/jobs.yaml`（测试/巡检）。
6. 执行下方 **§4 统一收尾**。

### C. Git 仓库登记

1. `git clone` 到 `projects/<slug>/`（Butler **不**自动 pull/push）。
2. 若无 `project.yaml`，从 `software-default.project.yaml` 复制并改 `name`、`tools`。
3. `butler project preflight --path projects/<slug>` 按建议补全。
4. §4 统一收尾。

**Claude Code / Cursor**：不登记为项目类型；本机 IDE 改代码与 Butler 项目 workspace 可指向同一路径，协调方式见规划文档 §2.4。

---

## 3. 体检命令

```bash
# 按目录
butler project preflight --path projects/DemoPilot

# 按已登记项目名
butler project preflight --project 灵文1号

# CI / 脚本
butler project preflight --path projects/MySlug --json
```

| 级别 | 含义 |
|------|------|
| FAIL | 必须修复（如缺 `project.yaml`） |
| WARN | 建议修复（MEMORY、pilot-setup、安全根） |
| INFO | 提示（模板建议、Lead 可选） |

退出码：`0` = 无 FAIL，`1` = 存在 FAIL。

---

## 4. 统一收尾（登记后必做）

| 步骤 | 命令 / 动作 |
|------|-------------|
| 1 | `butler project preflight` 无 FAIL |
| 2 | `butler memory-reindex --project "<name>"` |
| 3 | 若改 Skill / `.env`：`bash scripts/butler-gateway-ops.sh restart` |
| 4 | 微信：`/项目` → `/切换 <name>` → `/诊断` |
| 5 | Lead 项目：确认「对话引擎: 项目 Lead（厂长）」 |

---

## 5. 能力模板对照

| 模板 ID | 文件 | 何时用 |
|---------|------|--------|
| `software-default` | `software-default.project.yaml` | 通用软件仓库 |
| `novel-factory` | `novel-factory.project.yaml` | 含 `novel-factory/` |
| `knowledge-light` | `knowledge-light.project.yaml` | 仅文档/记忆（极少） |

preflight 会根据目录内容**建议**模板与标签（如 `pack:novel-factory`、`lifecycle:complete`）。

---

## 6. 微信验收最小集

在目标项目上：

1. `/状态` — 当前项目名正确。  
2. 只读探路 — 如 `读取 README 前 20 行`。  
3. 委派 — `委派开发代理：列出 docs/ 下文件`（Lead 不应直接改盘）。  
4. `/工作流 list` 或 `/运行 <job>`（若配置了 runtime）。  
5. `/诊断` — 项目、runtime、对话引擎一行无误。

灵文完整清单：[`projects/LingWen1/docs/pilot-setup.md`](../../projects/LingWen1/docs/pilot-setup.md)、[`wechat-daily-smoke-checklist.md`](wechat-daily-smoke-checklist.md)。

---

## 7. 协作速查（用户 · 管家 · 项目）

- **用户**：只对一个微信 Bot（莎丽）说话；用 `/切换` 选项目。  
- **管家**：Owner 画像、跨项目记忆、`/记忆` `/诊断` `/模型`。  
- **项目**：workspace + 项目 MEMORY + 可选 Lead + runtime。  
- **工人**：`delegate_task` 改代码；**runtime** 跑重复脚本。

冲突时：个人偏好 → Owner；工厂 phase/下一步 → 当前项目 Lead + `workflow_state.json`。

---

## 8. 相关文档

- [`projects/README.md`](../../projects/README.md)  
- [`architecture/project-layer-wechat-plan.md`](../architecture/project-layer-wechat-plan.md)  
- [`architecture/project-lead-decision.md`](../architecture/project-lead-decision.md)
