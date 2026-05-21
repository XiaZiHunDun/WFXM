# 灵文1号 · 记忆写入对照表

> Butler 记忆模块试点说明。正式灵文项目不在本仓库，勿混淆。

## 四层信息放哪

| 你要记的内容 | 放哪 | 工具 / 操作 |
|--------------|------|-------------|
| 称呼、微信回复长短、默认灵文1号 | Owner 画像 | `butler_remember` → `owner_profile`，或编辑 `~/.butler/tenants/default/memory/profile.json` |
| 灵文1号试点决策、架构、进度 | 项目记忆 | `butler_remember` → `project_notes` + `section`；**决策语气**会进 Pending（与 `/新对话` 提炼一致），用 `/批准记忆` 落盘 |
| 跨项目教训 | 全局经验库 | `butler_remember` → `owner_experience`；检索用 `butler_recall` |
| 上轮聊天说了啥 | **不长期保存** | 靠当前会话；`/新对话` 清空 |
| 《星陨纪元》章节、novel-factory 正文 | **文件本身** | `read_file` / 委派；**不要**写入 MEMORY.md |

## 微信常用话术

- 「请记住：……」→ 管家应调用 `butler_remember`（选对 scope）
- 「以前关于一致性检查说过什么」→ `butler_recall`
- `/新对话` → 清空聊天；若对话足够长，会提示「已提炼：长期记忆 +N 条」

## 环境变量（本机 `.env`）

| 变量 | 试点推荐 |
|------|----------|
| `BUTLER_DEFAULT_PROJECT` | `灵文1号`（**唯一**运行时默认项目来源） |
| `BUTLER_SYNC_CONVERSATION_MEMORY` | `0`（默认不把每轮聊天写入 experience；说「请记住」仍会同步该轮） |
| `BUTLER_TERMINAL_ALLOWLIST_EXTRA` | `python3,bash`（跑 novel-factory 脚本时需 `BUTLER_ENABLE_TERMINAL=1`） |
| `BUTLER_EXPERIENCE_PRUNE_DAYS` | `30`（清理超过 N 天的 conversation 回声；`0` 关闭） |
| `BUTLER_PREFETCH_*` | 预取长度上限（见 `.env.example`）；`/诊断` 可看分层条数 |
| `BUTLER_SEMANTIC_MEMORY` | `1`（试点已开）：本地 `memory_vectors.db` + hybrid 召回 |
| `BUTLER_QUEUE_PREFETCH` | `1`（试点已开）：上轮结束后后台 warm；`/诊断` 可看「预取缓存: 命中」 |
| `BUTLER_PREFETCH_PROJECT_HITS` | 项目 MEMORY 向量/关键词预取条数（默认 5） |

## 诊断

微信 `/诊断` 会显示：Owner 画像条数、Experience 长期/会话回声、项目 MEMORY（**含项目名**）正式条目与 Pending、向量条数与 model；有上轮对话时还有预取注入字数、**预取缓存命中**、**项目预取模式**（vector/keyword）。

## 验收记录（2026-05-21，主公确认）

| 步骤 | 内容 | 结果 |
|------|------|------|
| M1 | `/诊断`（无会话） | 灵文1号 MEMORY 4 条、Pending 0、向量 4 条（hashing-v1） |
| M2 | 「灵文试点统一测试是哪天？」（paraphrase） | 答 **2026-05-22** |
| 可选 | `/拒绝记忆`、`预取缓存命中` | 未测；见 [wechat-daily-smoke-checklist.md](../../docs/guides/wechat-daily-smoke-checklist.md) |

## 机读 facts（暂缓）

`projects/LingWen1/.butler/memory/facts.json` 由 `auto_extract` 从仓库扫描生成，**当前未接入** 每轮预取与 `butler_recall`。试点以 **MEMORY.md + Owner 画像 + experience** 为准；facts 仅保留代码占位，后续若接入会单独说明。

## 路线图

**向量语义（可选）**：`.env` 设 `BUTLER_SEMANTIC_MEMORY=1` 后启用 `memory_vectors.db`；默认 **本地 hashing**（无云）。可选 `BUTLER_EMBEDDING_PROVIDER=openai|minimax` 走对应 Embedding API（失败自动回退 hashing）。`butler_remember` 写入 fact/decision/Pending 会同步向量；`/批准记忆` 会移除待审向量并索引正式章节。`butler_recall` / 每轮预取走 **FTS + 向量混合**。默认 `BUTLER_SEMANTIC_MEMORY=0` 仅 FTS。

开启后建议重建索引（把已有 experience / MEMORY 写入向量表）：

```bash
cd ~/projects/WFXM
# .env 中 BUTLER_SEMANTIC_MEMORY=1
bash scripts/butler-memory-reindex.sh
# 或: PYTHONPATH=. python3 -m butler.main memory-reindex
```

方案见 [`docs/architecture/memory-roadmap.md`](../../docs/architecture/memory-roadmap.md)。

## 命令（记忆）

| 命令 | 作用 |
|------|------|
| `/记忆待审` | 列出 MEMORY Pending 队列（**微信与 CLI**） |
| `/批准记忆 1` / `/批准记忆 全部` | 写入正式章节 |
| `/拒绝记忆 1` / `/拒绝记忆 全部` | 从 Pending 移除并清理待审向量 |

`butler_remember` 的 `project_notes` 支持 `action`: `append`（默认）、`remove`、`replace`（`replace` 需 `old_content`），会同步更新向量索引。

| `/工作流 run novel-factory-status` | 只读汇报 `workflow_state.json` |

**分工**：`workflow_state.json` = 机读进度；`MEMORY.md` Notes = 人读摘要（勿整份 JSON 入库）。

## 路径

- Owner：`~/.butler/tenants/default/memory/profile.json`
- 项目：`projects/LingWen1/.butler/memory/MEMORY.md`
