# 灵文1号 · 记忆写入对照表

> Butler 记忆模块试点说明。正式灵文项目不在本仓库，勿混淆。

## 四层信息放哪

| 你要记的内容 | 放哪 | 工具 / 操作 |
|--------------|------|-------------|
| 称呼、微信回复长短、默认灵文1号 | Owner 画像 | `butler_remember` → `owner_profile`，或编辑 `~/.butler/tenants/default/memory/profile.json` |
| 灵文1号试点决策、架构、进度 | 项目记忆 | `butler_remember` → `project_notes` + `section`（Architecture/Decisions/Notes） |
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

## 微信命令（记忆）

| 命令 | 作用 |
|------|------|
| `/记忆待审` | 列出 MEMORY Pending 队列 |
| `/批准记忆 1` / `/批准记忆 全部` | 写入正式章节 |
| `/工作流 run novel-factory-status` | 只读汇报 `workflow_state.json` |

**分工**：`workflow_state.json` = 机读进度；`MEMORY.md` Notes = 人读摘要（勿整份 JSON 入库）。

## 路径

- Owner：`~/.butler/tenants/default/memory/profile.json`
- 项目：`projects/LingWen1/.butler/memory/MEMORY.md`
