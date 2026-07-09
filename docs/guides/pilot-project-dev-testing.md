# Butler 试点项目 · 开发测试指南

> **定位**：`projects/` 下当前项目（**灵文1号**、**普通试点项目**）均为 **Butler 平台测试试点**，尚未作为独立生产业务上线。  
> **主路径**：Butler 自带开发链（`delegate_task` + 文件工具 + dev terminal + VERIFY），非 `/cc-bridge`。

---

## 1. 两个试点分工

| 项目 | 目录 | 类型 | 测什么 |
|------|------|------|--------|
| **普通试点项目** | `projects/DemoPilot/` | `software` | 多项目切换、runtime、**轻量 dev 委派**、VERIFY 接仓库 pytest 子集 |
| **灵文1号** | `projects/LingWen1/` | Lead + novel-factory | 厂长剧本、content/dev/review 全链、workflow、记忆与真机运营 |

**默认自动化门禁**选 **普通试点项目**（快、无 novel-factory 依赖）。月度/深度委派仍跑 **灵文1号** track。

---

## 2. Agent 改动试点项目 — 预期行为

Butler / Cursor Agent 在验收与模拟中会 **直接改试点 workspace**，这是设计如此，不是污染：

| 来源 | 典型产物 | 是否可删 |
|------|----------|----------|
| `butler-wechat-dev-delegate-sim.sh` | `docs/dev-delegate-sim-*.md`、`.py` | ✅ sim 脚本 cleanup |
| `butler-wechat-dev-flywheel-sim.sh` | `docs/dev-flywheel-*.md` | ✅ 同上 |
| 真机 / 手动委派 | README 补丁、`.butler/delegate/*.task.md` | 按需保留作证据 |
| Runtime job | 无写盘（只读 pytest） | — |
| **平台 pytest** | 只动 `tests/`，**不**要求改试点目录 | — |

**原则**：

- 试点 **业务代码**（DemoPilot 几乎只有 README + docs）可被反复改写；以 **门禁脚本 PASS** 为准，不以目录 git 干净为准。
- 长期证据写 **`pilot-log`**（灵文1号在仓内；普通试点项目见 `projects/DemoPilot/docs/pilot-log.md`）。
- 模拟前脚本会按 manifest `cleanup_globs` 删当日 sim 文件，避免「文件已存在」导致用例失真。

---

## 3. 一键门禁（推荐）

```bash
cd /path/to/WFXM

# 默认：普通试点项目（software 第二条轨）
bash scripts/butler-pilot-dev-testing.sh

# 灵文1号委派全 track（慢，需 LLM）
bash scripts/butler-pilot-dev-testing.sh --project lingwen

# 跳过 handler 委派 sim（无 key / 省时）
bash scripts/butler-pilot-dev-testing.sh --no-delegate
```

### 脚本覆盖项

| 步骤 | 说明 |
|------|------|
| `butler project preflight` | 项目登记与健康 |
| `butler-demo-pilot-smoke.sh` | runtime heartbeat + test-unit-smoke |
| `butler-dev-live-flywheel-checklist.sh --probe` | env + `project.yaml` VERIFY |
| `butler-dev-tools-smoke.sh` | git/terminal/patch（**隔离临时目录**，非试点目录） |
| `butler-wechat-remote-dev-sim.sh` | `/沙箱` `/分工` handler |
| `butler-wechat-dev-delegate-sim.sh` | 委派 track（demopilot 或 lingwen） |

---

## 4. 分项命令

### 4.1 普通试点项目（CLI）

```bash
butler project preflight --project 普通试点项目
bash scripts/butler-demo-pilot-smoke.sh
bash scripts/butler-wechat-dev-delegate-sim.sh --track demopilot
```

项目内说明：[`projects/DemoPilot/docs/pilot-setup.md`](../../projects/DemoPilot/docs/pilot-setup.md)、[`pilot-flywheel.md`](../../projects/DemoPilot/docs/pilot-flywheel.md)。

### 4.2 灵文1号（委派 + 厂长）

```bash
bash scripts/butler-wechat-dev-delegate-sim.sh --track lingwen
bash scripts/butler-lingwen-live-capture-checklist.sh   # 每周
```

运营日志：[`projects/LingWen1/docs/pilot-log.md`](../../projects/LingWen1/docs/pilot-log.md)。

### 4.3 月度合成

```bash
bash scripts/butler-dev-flywheel-monthly.sh
```

见 [`dev-flywheel-monthly.md`](dev-flywheel-monthly.md)。

---

## 5. `project.yaml` dev 块（VERIFY）

试点必须配置非空的 `dev.lint_command` / `dev.test_command`（驱动 dev 子代理 VERIFY 与 `/测试`）：

- **普通试点项目**：指向仓库根 `../../tests/` 快测子集（见 `projects/DemoPilot/project.yaml`）
- **灵文1号**：`../../tests/dev_engine/` 等子集

沙箱 npm：`projects/DemoPilot/.butler/sandbox.json`（`networkPolicy.allow`）。

---

## 6. 微信真机（试点任选其一）

普通试点项目（约 5 分钟）：

```
/切换 普通试点项目
请委派开发代理：read_file README.md 前 15 行并中文摘要，不要改文件。
```

灵文1号飞轮（约 15 分钟）：见 [`dev-flywheel-monthly.md`](dev-flywheel-monthly.md) §2A。

---

## 7. 失败排查

| 现象 | 查 |
|------|-----|
| VERIFY SKIP/FAIL | `project.yaml` 命令、`--probe` 输出 |
| 委派未走 dev | `butler-wechat-dev-delegate-sim.sh --track …` |
| terminal 沙箱 | `/沙箱`、`BUTLER_TERMINAL_SANDBOX`、bwrap |
| 路径 `LingWen1/docs` | Lead Skill 路径纪律 |

---

## 8. 相关决策与架构

- [`butler-system-assessment-and-ops-2026-06.md`](../plans/decisions/butler-system-assessment-and-ops-2026-06.md)
- [`remote-dev-strategy-2026-06.md`](../plans/decisions/remote-dev-strategy-2026-06.md)
- [`v4-architecture.md`](../architecture/v4-architecture.md)
