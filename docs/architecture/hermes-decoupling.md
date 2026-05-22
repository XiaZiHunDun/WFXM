# Hermes 解耦路线图（已完成）

> 更新：2026-05-20  
> 原则：**有用算法迁入 `butler/`，`reference/` 只读对照，仓库内无 Hermes 运行时。**  
> 产品路径已 Butler 化；本文档保留阶段验收记录。

## 当前真实依赖（诚实状态）

| 路径 | `butler chat` / `exec` | `butler gateway` | 说明 |
|------|------------------------|------------------|------|
| `butler/core/agent_loop.py` | ✅ 唯一 Loop | ✅ 经 `message_handler` | **不** import `AIAgent` |
| `butler/transport/` | ✅ | ✅ | 自建 LLM 客户端 |
| `butler/tools/` | ✅ | ✅ | 自建工具与审计 |
| `butler/gateway/platforms/wechat_ilink.py` | ❌ | ✅ 唯一平台 | Butler 原生 iLink |
| `reference/hermes-agent/` | ❌ | ❌ | 本地只读对照（gitignore），提炼 diff 用 |

结论：**产品路径已完全 Butler 化**；微信网关无 Hermes 子进程；仓库内不再包含 `vendor/` Hermes 树。

## 目标架构（已达成）

```
用户 → butler/gateway/platforms/wechat  → ButlerMessageHandler → AgentLoop
```

`reference/hermes-agent` 仅用于本地对照与历史提炼，不参与 `pip install` 与 CI。

## 分阶段计划

### 阶段 A — Butler 零 Hermes import ✅

- [x] Agent Loop、Transport、工具在 `butler/core` + `butler/transport`
- [x] `post_session.from_hermes_agent` deprecated；v3 测试在 `tests/archive/`
- [x] 根 `pyproject` 仅 `butler-system`；微信见 `[wechat]` extra

### 阶段 B — 仅微信 Gateway ✅

- [x] `butler gateway` → 微信 iLink
- [x] 其它平台 CLI 拒绝；无 `--hermes-fallback`

### 阶段 C — 仓库整理 ✅

- [x] 曾迁 `vendor/hermes-agent/`；**已删除**（对照改 `reference/` 本地维护）
- [x] 根包仅 `butler` 脚本

### 阶段 D — 清理 ✅

- [x] 文档与 `STRUCTURE.md` 反映微信单平台

## 提炼 vs 依赖对照

| 做法 | 合理 | 不合理 |
|------|------|--------|
| 从 `reference/` 读片段，实现进 `butler/` | ✅ | |
| `import run_agent.AIAgent` 跑主对话 | | ❌ |
| 仓库内 vendored Hermes 当运行时 | | ❌ |

详见 [`hermes-extraction-map.md`](hermes-extraction-map.md)。

## 验收

- `rg '^from (agent|run_agent)' butler/` 无匹配  
- `butler gateway` 仅微信栈  
- 默认 `pytest` 1121 passed（`tests/archive/` 不收集；`live_llm` 需显式 `-m`）
