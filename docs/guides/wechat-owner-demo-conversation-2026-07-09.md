# 真人演示对话脚本（2026-07-09）

Handler 预演：

```bash
bash scripts/butler-wechat-owner-sim.sh \
  --manifest wechat-owner-demo-conversation-scenarios.yaml \
  --track owner-demo
```

## 推荐发送顺序（复制到微信）

前置：发 **`/新对话`**（个人管家模式，未绑项目）

| # | 你说 | 预期 |
|---|------|------|
| 1 | 莎丽，介绍一下你自己 | 个人管家 + 两项目名（普通试点项目、灵文1号） |
| 2 | 看下目前都有哪些项目 | 列表含 `[DemoPilot/]`、`[LingWen1/]` |
| 3 | 帮我搜一下XingWen项目在哪个路径 | `terminal find` → `/home/ailearn/projects/XingWen` |
| 4 | `/切换 灵文1号` | 进入厂长 Lead |
| 5 | `/项目待办` · `/任务` | 项目待办 / 最近委派 |
| 6 | 分析一下灵文1号的代码架构是否需要改进 | 只读分析（可能较长） |
| 7 | 看下项目目前都有哪些任务或者改进项待做 | 改进清单 |
| 7b | **`/新对话`** → **`/切换 灵文1号`** | 委派前清回声（必做） |
| 8a | **文档类**：见下方话术 | content 委派 → `docs/*.md` |
| 8b | **代码类**：见下方话术 | dev 委派 → `docs/*.py` |
| 9 | **`/新对话`** → **`/切换 灵文1号`** | 清委派回声后再测检索 |
| 10 | 看下我的github仓库都有哪些 | MCP GitHub |
| 11 | 搜索一下蚂蚁官网的信息 | `web_search` |
| 12 | 用firecrawl搜索一下蚂蚁官网的信息 | `mcp_firecrawl_*` |

### #8a 文档类（content）— 复制发送

```
选一个文档类改进项：交给内容代理，在 docs 写一份 owner-demo-文档验收.md，
标题写「Owner演示-文档验收」，正文带上今天日期和灵文1号，别动别的文件
```

### #8b 代码类（dev）— 复制发送

```
再选一个代码类改进项：交给开发代理，在 docs 建 owner-demo-dev.py，
写个 def owner_demo_ok(): return 42，写完后读一下确认，别动别的文件
```

## 演示注意

- **XingWen 搜索**依赖 `BUTLER_ENABLE_TERMINAL=1` 与 `BUTLER_TOOL_SAFE_ROOT=/home/ailearn/projects`。
- **GitHub / Firecrawl** 需 MCP 已启用。
- **8a / 8b 都跑完**再 `/新对话`，否则 #10–#12 可能夹带验收卡。
- 代码类务必说 **「开发代理 / role=dev」**，避免误走 content 或 run_workflow。
- 避免说「演示试点」；当前显示名为 **普通试点项目**。

## 口语替代（不推荐演示用）

- #5：`看下目前都有哪些任务` → 易绕 Todoist；用斜杠命令。
- #8：只说「选一个改进项来完善」→ 易 dev 改错路径；拆成 8a 文档 + 8b 代码两句。
