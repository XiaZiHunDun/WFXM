# Butler 维护者速查与面试手册

> **状态**：2026-07 | **读者**：Owner、运维、面试准备  
> **SSOT**：代码 + [`v4-architecture.md`](../architecture/v4-architecture.md) · 记忆运维 [`memory-ops.md`](memory-ops.md)

---

## 1. 三十秒电梯稿

Butler v4 是**自托管的多项目 AI 管家**：你在**微信**或 **CLI** 下指令，系统用自建的 **Agent Loop** 理解意图，通过 **`delegate_task`** 委派给 dev/content/review 等子代理在项目 workspace 里改代码或写内容；**分层记忆**跨会话延续上下文。

**典型路径**：`/切换 项目` → `/简报` → 「交给开发…」或 `/改` → 验收卡确认。

**不是什么**：全量 MCP Host、IDE 子进程替代 Loop、多租户 SaaS、浏览器自动化默认路径、LSP。

---

## 2. 消息链路

```
你（微信/CLI）
  → Platform Adapter（wechat_ilink）
  → ButlerMessageHandler（排队、去重、session）
  → ButlerOrchestrator（记忆、Skill、模型）
  → AgentLoop（压缩 → LLM → 工具 → …）
  → Report Pipeline（AgentReport、验收卡）
  → Outbound（微信文字/附件）
```

代码入口：[`butler/gateway/message_handler.py`](../../butler/gateway/message_handler.py) → [`session_loop_factory.py`](../../butler/gateway/session_loop_factory.py) → [`butler/core/agent_loop.py`](../../butler/core/agent_loop.py)。

---

## 3. 角色：你和谁对话？

Gateway 用 [`gateway_loop_role()`](../../butler/project/lead.py) 选 Loop 角色：

| 角色 | 何时 | 你能感受到的 |
|------|------|-------------|
| **lead** | 项目 `lead: true` 或 novel-factory 包 | 厂长：读状态 + 委派，微信 minimal 工具集不直接改盘 |
| **butler** | 普通项目（如演示试点） | 全局管家，工具较全 |
| **plan** | plan 模式 session | 只规划不执行 |
| **dev/content/review** | **不是你直接对话的对象** | `delegate_task` 开的子 Loop |

**要点**：你和 **Lead/Butler** 聊；改代码的是 **dev 子代理**（独立 session、独立工具、depth≤2）。

---

## 4. 记忆三层与存储

| 层 | 内容 | 路径（典型） |
|----|------|-------------|
| **Owner 管家层** | 画像、跨项目经验 | `~/.butler/memory/<tenant>/profile.json`、`experience.db`、`memory_vectors.db` |
| **项目层** | 架构/决策/约定 | `<workspace>/.butler/memory/MEMORY.md`、`facts.json` |
| **会话层** | 对话轨迹 | `~/.butler/sessions/<key>/transcript.jsonl` |

**原则**：Markdown/JSONL = **人读 SSOT**；SQLite = **可重建索引**（向量、FTS、observation）。详见 [`memory-ops.md`](memory-ops.md) §存储关系。

**统一召回（gateway lead 剖面，opt-in）**：`BUTLER_MEMORY_UNIFIED_RECALL=1` → `butler memory search --scope hybrid`；`BUTLER_MEMORY_OBSERVATION_RECALL=1` → `--scope observation`。`/诊断 详细` 可见各 scope 召回与「最近向量写入」。

---

## 5. 委派与安全

| 机制 | 说明 |
|------|------|
| `MAX_DELEGATE_DEPTH=2` | 防止无限套娃 |
| `DELEGATE_BLOCKED_TOOLS` | 子代理不能再 `delegate_task` |
| `filter_tools_for_subagent` | 子代理工具更窄 |
| `child_session_key` | `{parent}::delegate::{task_id}`，历史隔离 |
| `read-before-edit` | patch 前须 read_file |
| `permissions.yaml` | allow/deny/ask |
| **终端** | gateway 默认关；dev 子代理 / dev-local 可开 |

---

## 6. 上下文压缩（何时触发）

1. **主动**：估算 token ≥ `get_auto_compact_threshold()`，且消息 ≥ 12 条  
2. **被动**：API 413 → `reactive_compact`  
3. **策略**：先剪工具输出 → 分 head/middle/tail → 辅助模型摘要 middle → 压缩前抽 fact → 重注入锚点

---

## 7. LLM 与 Fallback

- **温度**：`ModelConfig.temperature` → `LLMClient` → API；低=稳（dev），高=创意（content）
- **Fallback 链**：主模型 API 失败时按 `llm_fallback` 换备用 Provider（可用性降级，非按任务类型）
- **Thinking 协议**：`BUTLER_THINKING_PROTOCOL=1` 时为推理模型加 system hint + Anthropic beta 头（默认关）

配置详见 [`reference.md`](../config/reference.md) §LLM 对话参数。

---

## 8. 常见面试题（简答）

**为何不用 Postgres？** 单租户自托管；文件 SSOT 可读可审；SQLite 只做派生索引，可 `reindex`。

**MCP Host vs 客户端？** 我们只做薄 MCP 客户端；不做 npm 级 Host/市场。

**CC 线束？** 对标 Claude Code CLI 的上下文经济、read-state、队列等回归测试：`./scripts/butler-cc-harness-gate.sh`。

**transcript.jsonl 与 transcript_fts.db？** jsonl 是真相源；fts.db 是 FTS5 索引，可 rebuild。

---

## 9. 运维命令速查

```bash
butler doctor
butler onboard --profile gateway
butler memory reindex
butler transcript index --rebuild
bash scripts/butler-pytest-fast-gate.sh
bash scripts/butler-cc-harness-gate.sh
```

改 `butler/core`、`butler/memory`、`butler/gateway` 后另跑：

```bash
PYTHONPATH=. pytest tests/test_premise_memory_theory.py tests/test_memory_metrics_benchmark.py -q
```

---

## 附录 A：三十分钟上手实验（不写代码）

| # | 做什么 | 期望 |
|---|--------|------|
| 1 | `butler project list` + `butler chat` 发一句「列出项目」 | 能列出 DemoPilot / 灵文1号 |
| 2 | 读 3 个文件各 ~50 行：`message_handler` → `session_loop_factory` → `agent_loop` | 能说出「谁创建 Loop」 |
| 3 | `butler doctor` | 看到部署剖面、Embedding 档位、Recall@3 |
| 4 | `BUTLER_SEMANTIC_MEMORY=0` vs `1` 下 `butler memory search "测试"` | 语义开时 paraphrase 更易命中 |
| 5 | 微信 `/诊断` + `/简报`（gateway 机） | 对话引擎 lead/butler、记忆分层、向量行数 |

**验收**：能手绘「微信 → Gateway → Loop → 委派 → 记忆」框图并答 10 个追问。

---

## 附录 B：G1-04 观测窗结案（07-31 后）

窗满后执行：

```bash
bash scripts/butler-g1-04-closure-check.sh
```

通过则更新 [`theory-implementation-gap-register-2026-06.md`](../plans/decisions/theory-implementation-gap-register-2026-06.md) G1-04 行为 ✅。
