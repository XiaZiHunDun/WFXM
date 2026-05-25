# OpenClaw 对标学习规划（Butler v4）

> **状态**：OC-P0–P2 已落地（2026-05）  
> **源码**：[reference/openclaw](../../reference/openclaw)（gitignore，本地对照）  
> **原则**：只借鉴设计，不嵌入 OpenClaw/Pi 运行时、零新依赖  
> **索引**：[README.md](README.md)

---

## 1. 边界

| 做 | 不做 |
|----|------|
| 前置压缩路由、AGENTS.md 节回灌、工具环检测 | 136 通道插件、Pi 嵌入式运行时 |
| reply 单飞准入、群聊 bot 环防护 | Gateway HTTP 多客户端、OAuth MCP |
| `butler doctor`、terminal argv 绑定、`delegate_yield` | Docker 沙箱、Memory dreaming SDK |

队列 steer/collect、post-compact 锚点、MCP 薄客户端见 [reference-learning-plan](reference-learning-plan-2026-05.md) / [butler-mcp-capability](butler-mcp-capability-2026-05.md)（已先行落地）。

---

## 2. Butler 映射（已落地）

| 项 | 模块 | 配置 / 命令 |
|----|------|-------------|
| OC-P0 前置压缩 | `butler/core/preemptive_compact.py` | `BUTLER_PREEMPTIVE_COMPACT=1`（默认开） |
| OC-P0 AGENTS 节回灌 | `butler/core/agents_md_sections.py` | `BUTLER_POST_COMPACT_AGENTS_SECTIONS` |
| OC-P0 标识符保留 | `compaction_prompt.py` | 压缩提示内嵌 |
| OC-P1 工具环检测 | `butler/core/tool_loop_detect.py` | `BUTLER_TOOL_LOOP_DETECTORS` |
| OC-P1 reply 单飞 | `butler/gateway/reply_admission.py` | 默认开 |
| OC-P1 bot 环防护 | `butler/gateway/bot_loop_guard.py` | `BUTLER_BOT_LOOP_GUARD=0` |
| OC-P2 安全审计 | `butler/ops/security_audit.py` | `butler doctor` |
| OC-P2 terminal 绑定 | `butler/tools/terminal_approval.py` | Owner `/批准执行` |
| OC-P2 委派 yield | `delegate_yield` 工具 | task_store |

---

## 3. OpenClaw 源码索引

| 能力 | 路径 |
|------|------|
| 前置压缩 | `src/agents/pi-embedded-runner/run/preemptive-compaction.ts` |
| Post-compact 节 | `src/auto-reply/reply/post-compaction-context.ts` |
| 工具环 | `src/agents/tool-loop-detection.ts` |
| Reply 准入 | `src/auto-reply/reply/reply-turn-admission.ts` |
| Bot 环 | `src/channels/turn/bot-loop-protection.ts` |
| 安全审计 | `src/security/audit.ts` |
| Exec 绑定 | `src/infra/exec-approvals.ts` |
| Subagent yield | `src/agents/tools/sessions-yield-tool.ts` |

---

## 4. 仍暂缓（OC-P3）

- Transcript 异步索引（jsonl 未超阈值则不做）
- 出站 human delay、memory dreaming cron

---

*对照完成：2026-05*
