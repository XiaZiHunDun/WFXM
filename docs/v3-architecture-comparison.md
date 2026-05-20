# Butler v3 架构文档

> **历史文档**：当前主线为 **Butler v4**（自建 Agent Loop）。请参阅 [`v4-architecture.md`](v4-architecture.md) 与 [`hermes-extraction-map.md`](hermes-extraction-map.md)。本文保留 v3 嵌入式 Hermes 方案说明供对照。

## 架构概述

Butler v3 采用**嵌入式混合方案** — 直接 `import` Hermes `AIAgent` 作为引擎，在其上叠加 Butler 的产品层（分层记忆、Skill 路由、DAG 编排、Agent 角色等）。不 Fork Hermes 任何代码，通过 constructor injection + plugin hooks 实现集成。

```
用户 ─→ CLI / 微信 / 20+ 平台
         │
         ▼
   Butler Orchestrator          ← 分层配置、记忆注入、Skill 路由
         │
         ▼
   Hermes AIAgent (直接 import)  ← 30+ Provider、50+ 工具、Agent Loop
         │
         ├─→ delegate_task       ← 子 Agent 委派
         ├─→ MemoryProvider      ← Butler 分层记忆插件
         └─→ Gateway Plugin      ← Butler 斜杠命令拦截
```

## 核心模块

### Butler 产品层 (~2.5k 行)

| 模块 | 路径 | 说明 |
|------|------|------|
| 集成入口 | `butler/main.py` | 直接 import AIAgent，交互式 CLI，流式 Rich 渲染 |
| 编排器 | `butler/orchestrator.py` | System prompt 注入、模型配置、Skill 路由 |
| Agent 角色 | `butler/agent_profiles.py` | dev/content/review 三角色系统 prompt |
| DAG 编排 | `butler/task_orchestrator.py` | 拓扑排序、真并行（`asyncio.to_thread`）、审批门控 |
| 后处理 | `butler/post_session.py` | 双通道（记忆 + 技能）后台提取 |
| 工具护栏 | `butler/tool_guardrails.py` | 循环检测、重复阻断、warn/block/halt 三级 |
| 记忆插件 | `butler/memory_plugin.py` | Hermes MemoryProvider 实现，sync_turn 触发后台提取 |
| 配置 | `butler/config.py` | 分层模型配置（全局 → 项目 → 运行时覆盖） |
| 全局记忆 | `butler/memory/butler_memory.py` | ProfileStore + ExperienceStore |
| 项目记忆 | `butler/memory/project_memory.py` | MarkdownMemory + ProjectFacts |
| Skill 管理 | `butler/skills/manager.py` | 完整 Skill 生命周期 |
| Skill 路由 | `butler/skills/router.py` | 基于相似度的 Skill 匹配 |
| Skill 合并 | `butler/skills/consolidator.py` | LLM 驱动的三层漏斗 + 自动合并 |
| 报告 | `butler/report.py` | CLI / WeChat 双格式 |
| 项目管理 | `butler/project_manager.py` | 多项目切换、隔离记忆上下文 |

### Hermes 插件

| 插件 | 路径 | 说明 |
|------|------|------|
| Memory Provider | `plugins/memory/butler/` | 注册 ButlerMemoryProvider，为 Hermes 提供分层记忆 |
| Gateway Hook | `plugins/butler/` | `pre_gateway_dispatch` 拦截 Butler 斜杠命令，支持 `skip`/`rewrite` 协议 |

### 直接使用的 Hermes 能力 (~300k 行)

- **30+ LLM Provider**: 含 fallback chain、credential pool、4 种协议
- **20+ Gateway**: Telegram/Discord/飞书/钉钉/Slack/Matrix/邮件/短信/微信等
- **50+ 工具**: 文件操作、shell、git、浏览器自动化(Playwright)、MCP
- **Agent Loop**: 上下文压缩、checkpoint、恢复、多轮对话
- **delegate_task**: 子 Agent 系统，context 隔离
- **Plugin 系统**: hooks、工具注册、可扩展架构
- **Dashboard**: Web SPA 管理界面
- **Cron**: 定时任务

## 痛点解决状态

| # | 痛点 | 解决方案 | 状态 |
|---|------|---------|------|
| 1 | 国产模型效果差 | Agent Profiles 中的国产模型 prompt 适配 + Hermes 30+ Provider | ✅ 已解决 |
| 2 | 同时只能一个模型 | 分角色 AIAgent 多实例，`/model <角色> <provider/model>` 按层切换 | ✅ 已解决 |
| 3 | 交互体验差 | Rich CLI 直接驱动 AIAgent，流式输出 + Markdown 渲染 | ✅ 已解决 |
| 4 | SubAgent 效果差 | DAG 编排 + `asyncio.to_thread` 真并行 + Agent Profiles | ✅ 已解决 |
| 5 | 微信按层切模型 | Gateway Plugin Hook 拦截 `/model` 命令，支持按角色配置 | ✅ 已解决 |
| 6 | 跨项目记忆混乱 | session key 隔离 + MemoryProvider 按项目注入上下文 | ✅ 已解决 |
| 7 | 会话记忆丢失 | sync_turn 累积 → 后台双通道提取（记忆 + 技能） | ✅ 已解决 |

## 测试覆盖（v3 时代快照）

```
tests/test_butler_v3.py — 44 tests PASSED（v3；v4 当前为 733+，见 v4-architecture.md）

TestIntegrationBridge     — 5 tests (AIAgent 构建, 配置注入)
TestMemoryPlugin          — 4 tests (注册, 工具, sync_turn)
TestButlerPlugin          — 6 tests (hook 注册, slash 命令, dataclass 兼容)
TestAgentProfiles         — 6 tests (角色配置, 国产模型适配)
TestToolGuardrails        — 6 tests (循环检测, 阻断, 重置)
TestPostSessionProcessor  — 3 tests (跳过, mock LLM, 工厂方法)
TestTaskOrchestrator      — 3 tests (拓扑排序, 并行, 环检测)
TestOrchestrator          — 4 tests (prompt, memory, skills)
TestConfigOverrides       — 2 tests (运行时覆盖, 分层配置)
TestMainSlashCommands     — 5 tests (help, projects, status, quit)
```

## 关键架构优势

1. **零 Fork**: 不修改 Hermes 任何一行代码，通过 constructor injection + plugin hooks 集成
2. **可跟随上游**: Hermes 更新只需 `git pull`，Butler 层独立维护
3. **v1 产品逻辑完整保留**: DAG 编排、Agent Profiles、Tool Guardrails、PostSession 全部移植并适配
4. **即刻获得 Hermes 生态**: 20+ Gateway 和 30+ Provider 开箱即用
5. **CLI 深度集成**: Butler 交互式 CLI 直接驱动 Hermes AIAgent，流式 Rich 渲染
6. **真并行执行**: `asyncio.to_thread` 包装同步阻塞调用，DAG 并行任务实际并行
7. **插件协议规范**: Gateway Plugin 正确使用 Hermes `MessageEvent` dataclass 和 action dict 协议
