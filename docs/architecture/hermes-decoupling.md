# Hermes 解耦路线图

> 更新：2026-05-20  
> 原则：**有用算法迁入 `butler/`，`reference/` 只读对照，运行时不再依赖 Hermes 黑盒 Agent。**

## 当前真实依赖（诚实状态）

| 路径 | `butler chat` / `exec` | `butler gateway` | 说明 |
|------|------------------------|------------------|------|
| `butler/core/agent_loop.py` | ✅ 唯一 Loop | ✅ 经 `message_handler` | **不** import `AIAgent` |
| `butler/transport/` | ✅ | ✅ | 自建 LLM 客户端 |
| `butler/tools/` | ✅ | ✅ | 自建工具与审计 |
| `agent/`、`run_agent.py` | ❌ 不 import | ⚠️ Gateway 子进程内部 | Hermes Agent 黑盒 |
| `gateway/` + `hermes_cli` | ❌ | ⚠️ `subprocess` 启动 | 20+ 平台适配器仍在 Hermes |
| `plugins/memory/butler/` | ❌ | ⚠️ Hermes 插件 ABI | 已通过 `hermes_bridge` 隔离 |
| `reference/` | ❌ | ❌ | 仅提炼对照，**禁止改动** |

结论：**对话主路径已解耦 Loop**；**多平台 Gateway 仍是最大技术债**，与「整包 Hermes 躺在仓库根目录」是两件相关但不等同的事。

## 目标架构

```
用户 → butler/gateway/platforms/*  → ButlerMessageHandler → AgentLoop
                ↑
         不再 subprocess hermes gateway run
```

仓库根目录的 `agent/`、`run_agent.py`、`gateway/` 最终应：

1. **迁出**到 `vendor/hermes-agent/`（子模块/可选依赖），或  
2. **删除**（Gateway 平台代码已迁入 `butler/gateway/platforms/`）

`reference/hermes-agent` 始终保持只读，供提炼 diff，不参与 `pip install` 运行时。

## 分阶段计划

### 阶段 A — Butler 零 Hermes import（进行中 / 大部分完成）

- [x] Agent Loop、Transport、工具批次在 `butler/core` + `butler/transport`
- [x] `butler/config` 不再 `import hermes_constants`
- [x] `ButlerMemoryService` 与 `plugins/memory/butler/hermes_bridge` 分离
- [x] 后台记忆提炼改用 `auxiliary_client`（修复旧 `_create_butler_agent` 死代码）
- [ ] `post_session.from_hermes_agent` 标为 deprecated，测试迁出 v3 路径
- [ ] `pyproject` 将 Hermes 包标为 optional extra（`butler-system[hermes-gateway]`）

### 阶段 B — Butler 原生 Gateway（高优先级）

- [x] `butler gateway` 默认进程内启动 `ButlerMessageHandler` + 平台 adapter（`butler/gateway/runner.py`）
- [x] 首期平台：**微信 iLink**（`butler/gateway/platforms/wechat_ilink.py`，提炼自 Hermes `weixin` 适配器）
- [x] `--hermes-fallback` 保留 Hermes 子进程路径（Telegram 等未迁入平台）
- [ ] 迁入更多平台适配器；逐步废弃 `plugins/butler` Hermes hook

### 阶段 C — 仓库物理整理

- [ ] 根目录 Hermes 树移入 `vendor/hermes-agent/`（**不**动 `reference/`）
- [ ] `STRUCTURE.md` / CI 只测 `butler` + `tests/`
- [ ] 控制台 `hermes` / `hermes-agent` 脚本改为 optional 或独立包

### 阶段 D — 清理

- [ ] 删除未使用的 `test_butler_v3` AIAgent 路径（或移入 `archive/`）
- [ ] 文档统一：不再写「仅 Gateway subprocess」为终态

## 提炼 vs 依赖对照

| 做法 | 合理 | 不合理 |
|------|------|--------|
| 从 `reference/` 读片段，实现进 `butler/` | ✅ | |
| `import run_agent.AIAgent` 跑主对话 | | ❌ |
| 复制算法到 `butler/core`，单测覆盖 | ✅ | |
| 根目录整包 Hermes 当运行时库 | | ❌（过渡态） |
| Gateway 平台 **提炼** 到 `butler/gateway/platforms` | ✅ | |
| 长期 `subprocess hermes gateway run` | | ❌ |

详见 [`hermes-extraction-map.md`](hermes-extraction-map.md)。

## 验收

- `rg '^from (agent|run_agent)' butler/` 无匹配  
- `butler chat` / `butler exec` 不启动 Hermes 子进程  
- `butler gateway --platforms wechat` 仅走 Butler 栈（阶段 B 完成后）  
- 默认 `pytest` 733+ 通过
