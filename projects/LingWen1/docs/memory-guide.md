# 灵文1号 · 记忆写入对照表

> Butler 记忆模块试点说明。正式灵文项目不在本仓库，勿混淆。

## 四层信息放哪

| 你要记的内容 | 放哪 | 工具 / 操作 |
|--------------|------|-------------|
| 称呼、微信回复长短、默认灵文1号 | Owner 画像 | `butler_remember` → `owner_profile`，或编辑 `~/.butler/tenants/default/memory/profile.json` |
| 灵文1号试点决策、架构、进度 | 项目记忆 | `butler_remember` → `project_notes` + `section`；**决策语气**会进 Pending（与 `/新对话` 提炼一致），用 `/批准记忆` 落盘 |
| 跨项目教训 | 全局经验库 | `butler_remember` → `owner_experience`；检索用 `butler_recall` |
| 上轮聊天说了啥 | **不长期保存** | 靠当前会话；`/新对话` 清空上下文（长期记忆仍在） |
| 《星陨纪元》章节、novel-factory 正文 | **文件本身** | `read_file` / 委派；**不要**写入 MEMORY.md |
| 流水线机读进度 | `novel-factory/workflow_state.json` | 只读 `read_file` 或 `/工作流 run novel-factory-status`；**勿整份 JSON 入库** |

## 写入边界（必守）

| 场景 | 正确做法 | 禁止 |
|------|----------|------|
| 用户说「请记住…」 | `butler_remember` + 正确 scope | 只口头答应 |
| 决定/采用/迁移 | `project_notes` → 往往 **Pending** | 直接当已批准写进 Decisions |
| 问「以前关于 X 说过什么」 | `butler_recall` 或自然提问（预取） | 编造未写入内容 |
| 技术栈/目录结构 | 预取 **Project facts (auto)** + `read_file` | 把 pyproject 全文塞进 MEMORY |
| 360 章正文、发布稿 | `read_file` / 委派 content | `butler_remember` |

## 生产环境推荐（`.env`）

| 变量 | 灵文试点推荐 | 说明 |
|------|-------------|------|
| `BUTLER_DEFAULT_PROJECT` | `灵文1号` | 微信默认项目 |
| `BUTLER_SEMANTIC_MEMORY` | **`1`** | 向量 + hybrid；关则仅 FTS |
| `BUTLER_QUEUE_PREFETCH` | **`1`** | 上轮结束后 warm；同句复问更快 |
| `BUTLER_SYNC_CONVERSATION_MEMORY` | **`0`** | 不把每轮闲聊写入 experience |
| `BUTLER_EXPERIENCE_PRUNE_DAYS` | `30` | 清理历史 conversation 回声 |
| `BUTLER_PREFETCH_*` | 见 `.env.example` | `/诊断` 可看预取字数与缓存命中 |
| `BUTLER_PREFETCH_FACTS_MAX_CHARS` | `400` | facts 预取块上限 |
| `BUTLER_MEMORY_HALF_LIFE_DAYS` | `30` | 检索时间衰减半衰期 |
| `BUTLER_MEMORY_ACCESS_BOOST` | `0.12` | 访问次数排序加权 |
| `BUTLER_TERMINAL_ALLOWLIST_EXTRA` | `python3,bash` | 跑 novel-factory 时需 `BUTLER_ENABLE_TERMINAL=1` |

**发版或升级记忆模块后**（不仅改 MEMORY 时）建议执行一次：

```bash
cd ~/projects/WFXM
bash scripts/butler-memory-reindex.sh
```

改 MEMORY / 批量 `/批准记忆` 后亦建议：

```bash
cd ~/projects/WFXM
bash scripts/butler-memory-reindex.sh
```

## 运维检查表（发版 / 每周）

| # | 检查项 | 通过标准 |
|---|--------|----------|
| O1 | `.env` 语义记忆与 queue_prefetch 已开 | `BUTLER_SEMANTIC_MEMORY=1`、`BUTLER_QUEUE_PREFETCH=1` |
| O2 | reindex 无报错 | `bash scripts/butler-memory-reindex.sh` 输出 `ok: true` |
| O3 | 自动化守门 | `bash scripts/butler-memory-smoke.sh` 全绿 |
| O4 | `/诊断` 静态 | 有项目名、MEMORY 条数、向量条数、embedding model |
| O5 | Pending 不堆积 | `/记忆待审` 为空或已处理 |
| O6 | MEMORY 无重复/过时大段 | 人工扫 Notes/Decisions，删重复 bullet |
| O7 | 画像向量与三元组 | `/诊断` 有 Owner 画像向量条数；`/记忆图谱` 可列出三元组 |
| O8 | 检索衰减参数 | `/诊断` 显示半衰期与访问加权（与 `.env` 一致） |
| O9 | 会话回声修剪 | `memory-offline-weekly` 已启用（周日 03:00）；或 `butler runtime run memory-offline-weekly --project 灵文1号` |

周期表与分层说明：[`docs/guides/memory-ops.md`](../../../docs/guides/memory-ops.md) §记忆卫生。

## 微信常用话术

- 「请记住：……」→ 管家应调用 `butler_remember`（选对 scope）
- 「以前关于一致性检查说过什么」→ `butler_recall`
- `/新对话` → 清空**本轮聊天**；长期记忆仍在；足够长时会提示「已提炼：长期记忆 +N 条」

## 真机冒烟（记忆效果）

| 步骤 | 发送 | 期望 |
|------|------|------|
| M1 | `/诊断`（无会话） | 灵文1号、MEMORY/向量条数、语义 model、三元组/衰减行 |
| M1b | `/记忆图谱` | 展示最近三元组（仅展示，不参与检索） |
| M2 | 「灵文试点统一测试是哪天？」（换说法） | 答出 MEMORY 中日期（如 2026-05-22） |
| M3 | 决策句 → `/记忆待审` → `/批准记忆 1` 或 `/拒绝记忆 1` | Pending 行为正确 |
| M4 | 同句连发两遍 → `/诊断` | **预取缓存: 命中**（间隔 20–90s） |
| M5 | 「项目用什么技术栈 / 顶层有哪些目录？」 | 回答含 facts 或 novel-factory；`/诊断` 有 **Project facts** 相关预取 |
| M6 | `/新对话` → 「我们刚才聊过什么？」 | **不**复述上轮闲聊细节；可提示已清空上下文 |
| M7 | 「请记住：试点验收日 2026-05-22」→ `/记忆待审` → `/批准记忆 全部` | 批准后 paraphrase 可召回 |

记录结果到 `pilot-log.md`（或 `bash scripts/butler-memory-monthly-probe.sh --log` 自动化 PASS 后追加一行）。

## 记忆质量运营

- **每月**：扫 Pending、重复 bullet、过时 Notes；必要时 `remove`/`replace`（`butler_remember` action）
- **扩召回回归**：编辑 `tests/fixtures/memory_recall/cases.json` 后跑 `butler-memory-smoke.sh`
- **角色预取**：厂长 thread 偏 Architecture/Decisions/Notes；content 偏 Notes/Patterns；见 `sections_for_agent_role`

## 诊断

微信 `/诊断` 会显示：Owner 画像条数、Experience 长期/会话回声、项目 MEMORY（**含项目名**）正式条目与 Pending、向量条数与 model、**Owner 画像向量** / **三元组（仅展示）** / **检索衰减** 参数；有上轮对话时还有预取注入字数、**预取缓存命中**、**项目预取模式**（vector/keyword）。

## 验收记录

| 批次 | 步骤 | 结果 |
|------|------|------|
| 2026-05-21 | M1–M4 首轮 | 主公确认通过 |
| 2026-05-22 | M1–M4、M1b、O7 复验 | ☑（M2 需 MEMORY 含「统一测试日 2026-05-22」后 reindex） |

**日期备忘**：**首轮微信验收** 2026-05-21 ≠ **统一测试日（M2）** 2026-05-22。

**后续**：`/新对话` post_session 写入项目 MEMORY 后会同步 `memory_vectors.db`；facts 在切换项目/reindex 时刷新。

## 机读 facts（auto）

`projects/LingWen1/.butler/memory/facts.json` 在 **切换项目**、**memory-reindex** 时由 `auto_extract` 刷新。每轮预取注入 **Project facts (auto)**；`butler_recall` 可用 `scope=project`。

## 多智能体 / 厂长模式

平台决策见 [`docs/architecture/project-lead-decision.md`](../../../docs/architecture/project-lead-decision.md)；灵文 Lead 五条能力与禁止项见 [`project-lead-scope.md`](project-lead-scope.md)。

## 路线图

向量语义见 [`docs/architecture/memory-roadmap.md`](../../../docs/architecture/memory-roadmap.md)。

## 命令（记忆）

| 命令 | 作用 |
|------|------|
| `/记忆待审` | 列出 MEMORY Pending 队列（**微信与 CLI**） |
| `/记忆图谱` | 三元组只读展示（**微信与 CLI**） |
| `/批准记忆 1` / `/批准记忆 全部` | 写入正式章节 |
| `/拒绝记忆 1` / `/拒绝记忆 全部` | 从 Pending 移除并清理待审向量 |

`butler_remember` 的 `action`：`project_notes` 与 `owner_profile` 均支持 `append`（默认）、`remove`、`replace`（画像 remove/replace 需 `old_content` 匹配原条目）。

| `/工作流 run novel-factory-status` | 只读汇报 `workflow_state.json` |

## 路径

- Owner：`~/.butler/tenants/default/memory/profile.json`
- 项目：`projects/LingWen1/.butler/memory/MEMORY.md`

## 本地脚本

```bash
bash scripts/butler-memory-smoke.sh    # recall fixture 回归
bash scripts/butler-memory-reindex.sh    # 重建向量索引
```
