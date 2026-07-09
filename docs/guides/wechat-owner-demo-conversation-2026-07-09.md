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
| 5 | `/项目待办` 或 `/任务` | 项目待办 / 最近委派（比口语「都有哪些任务」更稳） |
| 6 | 分析一下灵文1号的代码架构是否需要改进 | 只读分析（可能较长，等 1–2 条推送） |
| 7 | 看下项目目前都有哪些任务或者改进项待做 | 基于 MEMORY/roadmap 的改进清单 |
| 8 | 选一个文档类的改进项，委派内容代理写进 docs，别动代码 | 内容委派 + 验收卡 |
| 9 | **`/新对话`** → **`/切换 灵文1号`** | 清掉委派回声后再测检索 |
| 10 | 看下我的github仓库都有哪些 | MCP GitHub（勿 web_search） |
| 11 | 搜索一下蚂蚁官网的信息 | `web_search` |
| 12 | 用firecrawl搜索一下蚂蚁官网的信息 | `mcp_firecrawl_*` |

## 演示注意

- **XingWen 搜索**依赖 `BUTLER_ENABLE_TERMINAL=1` 与 `BUTLER_TOOL_SAFE_ROOT=/home/ailearn/projects`。
- **GitHub / Firecrawl** 需 MCP 已启用；微信 toolset 会自动放行 `mcp_*` 与 `web_search`。
- 委派步骤（#8）完成后建议 **`/新对话`**，否则后续回复可能夹带旧验收卡。
- 避免说「演示试点」；当前显示名为 **普通试点项目**。

## 口语替代（可选）

- #5：`看下目前都有哪些任务` → 可能绕远查 Todoist；优先用斜杠命令。
- #8：`选一个改进项来完善` → 易触发 dev 委派失败；改用「文档类 + content + docs」。
