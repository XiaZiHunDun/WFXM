# WFXM 整理与瘦身方案（2026-05）

> **状态**：**P0–P2 已完成**（2026-05-22）  
> **目标**：消化开发期熵增，让骨架与脉络重新清晰，**不**改变 v4 运行时架构。  
> **基线**：全量 pytest **1093 passed**（P1 移除 v3 archive 后），1 skipped，18 deselected；`butler-pre-release-smoke.sh` 9 步全绿。

---

## 1. 范围与边界

### 1.1 在范围内

| 区域 | 整理方式 |
|------|----------|
| `butler/` | 删除死代码、统一命名表述、保留模块结构 |
| `projects/` | 文档合并、试点说明收口 |
| `docs/` | 去重、跳转桩删除、规划稿归档、配置总表 |
| `scripts/` | 索引 README、去孤儿脚本、冒烟路径澄清 |
| `tests/` | 删除 archive/v3、瘦身 `test_butler_v4.py` |
| `archive/` | 迁 tag 后移出主树（`butler-v1`） |
| `vendor/` | 删除本地副本 + `.gitignore`（与 decoupling 文档一致） |
| `pyproject.toml` | 移除未使用依赖 |
| 根目录 `README.md`、`STRUCTURE.md` | 与现状对齐 |

### 1.2 明确不动

| 路径 | 原因 |
|------|------|
| **`reference/`** | **由主公维护**，用于外部竞品/标本对照；本方案**不删除、不迁移、不改 .gitignore 策略** |
| `projects/LingWen1/novel-factory/` | 领域生产树，仅文档与 runtime 边界整理 |
| Agent Loop / 微信网关核心逻辑 | 非重构，仅死代码与文档 |

### 1.3 原则

1. 运行时零依赖 `archive/`（迁出后）。  
2. 一个主题一份真相源（测试数、工具名、接入、冒烟）。  
3. 删之前先留档：`archive/butler-v1` → git tag。  
4. **每阶段结束**跑 `bash scripts/butler-pre-release-smoke.sh`。

---

## 2. 目标骨架（术后）

```text
用户（微信 / CLI）
    ↓
butler/                         # 唯一产品代码
    gateway · core · transport · tools
    memory · skills · runtime · workflows
    project / project_lead / project_preflight

projects/
    LingWen1/                     # 领域样板
    DemoPilot/                    # 平台样板

docs/
    architecture/               # ADR + v4 真相源
    guides/                       # 运维 / 冒烟 / 接入
    config/                       # reference.md 配置总表
    plans/                        # 本方案
    history/                      # v1/v3 对照

scripts/                        # README 矩阵

reference/                      # 【不动】主公维护的对照区
```

---

## 3. 熵增清单（摘要）

| 类型 | 代表 | 处理 |
|------|------|------|
| 历史未收口 | `archive/butler-v1/`、`tests/archive/` | P1 删除 / P2 迁 tag |
| 文档双轨 | 根 `docs/*.md` 跳转桩、双份手工测试 | P0/P1 合并删除 |
| 规划稿 | `project-layer-wechat-plan.md` | P0 标已落地 |
| 依赖胖 | `pyproject.toml` Hermes 遗留包 | P1 审计删除 |
| 配置散 | 71 `BUTLER_*`，example 缺项 | P0 `config/reference.md` |
| 脚本无索引 | 20+ `scripts/*.sh` | P0 `scripts/README.md` |
| 命名遗留 | `edit_file` 文档、`hermes_*` 死 API | P1 |
| Skill 双扫 | preflight 重复列 Skill | P0 去重 |
| 本地 vendor | `vendor/hermes-agent/` | P0 删除 + gitignore |
| 缺失脚本 | `butler-lingwen-lead-smoke.sh` | P1 实现或删引用 |

---

## 4. 分阶段执行

### P0 — 澄清脉络（不改行为）

| ID | 任务 | 验收 |
|----|------|------|
| P0.1 | 更新 `STRUCTURE.md`、`docs/README.md` | 含 DemoPilot、runtime、project CLI |
| P0.2 | 新增 `scripts/README.md` | 安装/日常/发版/冒烟矩阵 |
| P0.3 | 新增 `docs/config/reference.md` | BUTLER_* 分组表 |
| P0.4 | 测试数 **1121 → 1138+** 全文同步 | grep 无遗漏 |
| P0.5 | `project_preflight` Skill basename 去重 | 灵文体检不重复 |
| P0.6 | `project-layer-wechat-plan.md` 标已落地 | 链 onboarding |
| P0.7 | 删除 `vendor/` + `.gitignore` vendor | 不动 reference |
| P0.8 | 修文档硬伤（install 路径、lead-smoke 引用） | 无死链 |

### P1 — 瘦身减负

| ID | 任务 | 验收 |
|----|------|------|
| P1.1 | `pyproject.toml` 依赖审计删除 | 干净 venv `pip install -e ".[wechat]"` |
| P1.2 | 删 `tests/archive/`、`archive/butler-v1/tests/` | pytest 全绿 |
| P1.3 | 瘦身 `tests/test_butler_v4.py` | 去重覆盖 |
| P1.4 | 合并 `manual-testing-guide` + `cli-manual-test-cases` | 单入口 |
| P1.5 | 删 Hermes 死 API | `from_hermes_agent` 等 |
| P1.6 | 工具名文档统一为 patch/search_files/terminal | 一处别名表 |
| P1.7 | 实现 `scripts/butler-lingwen-lead-smoke.sh` | 或删全部引用 |
| P1.8 | 删除根目录 doc 跳转桩（7 个） | 链接已改 |
| P1.9 | Skill 流程写入 onboarding | git skills → sync → .butler/skills |

### P2 — 架构性收口（可选）

| ID | 任务 | 验收 |
|----|------|------|
| P2.1 | `archive/butler-v1` git tag 后移出 main | 仅留 `archive/README.md` |
| P2.2 | `docs/design/design.md` 历史迁 `docs/history/` | 正文 v4-only |
| P2.3 | 冒烟分层 runner（可选） | `butler-smoke.sh --tier=` |
| P2.4 | 稳定配置迁 `config.yaml`（可选） | env 仅密钥 |

---

## 5. 保留 / 删除 / 合并 速查

### 保留

- 全部 `butler/` 产品模块  
- `projects/LingWen1`、`projects/DemoPilot`  
- `docs/architecture/v4-architecture.md`、`project-lead-decision.md`、`hermes-decoupling.md`  
- `docs/guides/project-onboarding.md`、`wechat-daily-smoke-checklist.md`  
- `scripts/butler-gateway-ops.sh`、`butler-pre-release-smoke.sh`、install-*、systemd/

### 合并

- 手工测试双文档 → 一本  
- `wechat-smoke.md` → `pilot-setup.md`  
- 配置说明 → `docs/config/reference.md`  

### 删除（不含 reference）

- `vendor/`（本地）  
- `archive/butler-v1/tests/`  
- `tests/archive/`（tag 后）  
- 根 `docs/*` 跳转桩  
- `scripts/install-tesseract-user-local.sh`（若无引用）  
- 未使用的 pyproject 依赖  

---

## 6. 度量

| 指标 | 当前 | 目标 |
|------|------|------|
| pytest passed | 1093 | 全绿（P1 删 v3 archive 后） |
| README 测试数 | 1121（过期） | 1138+ |
| 根 docs 跳转桩 | 7+ | 0 |
| 手工测试入口 | 2+ | 1 |
| pre-release smoke | 通过 | 每阶段通过 |

---

## 7. 相关文档

- [项目评估（2026-05）](../reviews/project-assessment-2026-05.md)（若已创建）  
- [项目接入指南](../guides/project-onboarding.md)  
- [Hermes 解耦（已完成）](../architecture/hermes-decoupling.md)

---

## 8. 执行记录

| 日期 | 阶段 | 说明 |
|------|------|------|
| 2026-05-22 | 方案 | 本文档；**reference/ 排除**（主公维护） |
| 2026-05-22 | **P0 完成** | STRUCTURE、scripts/README、config/reference、1138 同步、preflight Skill 去重、vendor gitignore、规划稿归档 |
| 2026-05-22 | **P1 完成** | 依赖/archive 清理、test_butler_v4 瘦身、CLI 手册合并、lead smoke、死 API 删除（**reference/ 未动**） |
| 2026-05-22 | **P2 完成** | v1 → git tag；design 历史迁出；`butler-smoke.sh`；config.yaml 分工文档 |

### P0 交付清单

- [x] `docs/plans/consolidation-2026-05.md`（本文档）
- [x] `scripts/README.md`
- [x] `docs/config/reference.md`
- [x] `STRUCTURE.md` / `docs/README.md` 更新
- [x] 测试数 1138 同步（主要文档）
- [x] `project_preflight` Skill 去重
- [x] `project-layer-wechat-plan.md` 标已落地
- [x] `.gitignore` 增加 `vendor/`（**未动 reference/**）
- [x] **P1 完成**（2026-05-22）：依赖瘦身、删 archive 测试、瘦身 test_butler_v4、合并 CLI 手册、删 Hermes API、工具别名表、lingwen lead smoke、删根跳转桩

### P1 交付清单

- [x] P1.1 `pyproject.toml` 移除未用 Hermes 遗留依赖
- [x] P1.2 删 `tests/archive/`、`archive/butler-v1/tests/`
- [x] P1.3 瘦身 `tests/test_butler_v4.py`
- [x] P1.4 合并 `cli-manual-test-cases` → `manual-testing-guide` 附录 A
- [x] P1.5 删除 `PostSessionProcessor.from_hermes_agent`
- [x] P1.6 `docs/config/reference.md` 工具别名表
- [x] P1.7 `scripts/butler-lingwen-lead-smoke.sh` + pre-release 第 7 步
- [x] P1.8 删除根 `docs/*` 跳转桩（保留 `manual-test-guide.md` → history）
- [x] P1.9 onboarding Skill 同步流程
- [x] **P2 完成**（2026-05-22）：v1 迁 tag、design 历史拆分、butler-smoke 分层、config 稳定项文档

### P2 交付清单

- [x] P2.1 标签 `archive/butler-v1-20260522`，删除 `archive/butler-v1/`，仅留 `archive/README.md`
- [x] P2.2 `design-evolution-v0.5-v1.0.md`；`design/design.md` v4 摘要 + 附录
- [x] P2.3 `scripts/butler-smoke.sh --tier=quick|standard|full`
- [x] P2.4 `config/reference.md` + `config.yaml.example` 稳定项 vs 密钥分工
