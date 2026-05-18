# Butler v1 / v2 / v3 架构对比验证

## 架构总览

| 特性 | v1 (archive) | v2 (Fork + Layer) | **v3 (嵌入式混合)** |
|------|-------------|-------------------|---------------------|
| 引擎 | 自研 AgentRunner (~600行) | Hermes subprocess 调用 | **Hermes AIAgent 直接 import** |
| LLM Provider | 3个自研 (Claude/DeepSeek/MiniMax) | Hermes 30+ Provider (未接入) | **Hermes 30+ Provider (直接使用)** |
| Gateway | 2个 (CLI + WeChat) | Hermes 20+ (未接入) | **CLI 内嵌 + Hermes 20+ (Plugin Hook)** |
| 记忆系统 | 分层实现 (Profile/Experience/Project) | Butler层完整 但未注册 | **MemoryProvider 插件注册 + 后台提取** |
| Skill 系统 | 完整 (Manager/Router/Consolidator) | Butler层完整 | **复用 Butler 层 + Hermes Skill 系统** |
| DAG 编排 | 完整实现 但未接入运行时 | 无 | **移植 + 适配 Hermes AIAgent** |
| Agent Profiles | 3个角色 (Dev/Content/Review) | 无 | **移植为 ephemeral_system_prompt** |
| Tool Guardrails | 完整实现 | 无 | **移植完整** |
| PostSessionProcessor | 完整实现 | sync_turn 空操作 | **接入 sync_turn + 后台提取** |
| 模型分层配置 | LayeredModelConfig | 代码存在但未接线 | **接入 + 运行时覆盖 /model 命令** |

## 痛点解决验证

| # | 痛点 | v1 | v2 | **v3** |
|---|------|----|----|--------|
| 1 | 国产模型效果差 | ✅ 有 prompt 蒸馏 | ❌ 未接入 | ✅ **移植 prompt 适配 + Hermes 30+ Provider** |
| 2 | 同时只能一个模型 | ✅ LayeredModelConfig | ❌ 代码在但没用 | ✅ **分角色 AIAgent 多实例** |
| 3 | 交互体验差 | ✅ Rich CLI | ❌ subprocess | ✅ **Rich CLI + Hermes 引擎直接驱动** |
| 4 | SubAgent 效果差 | ⚠️ DAG 代码有但未接入 | ❌ | ✅ **DAG + Hermes AIAgent 执行** |
| 5 | 微信按层切模型 | ✅ /model 命令 | ❌ | ✅ **Plugin Hook 处理 /model** |
| 6 | 跨项目记忆混乱 | ✅ session key 隔离 | ❌ | ✅ **session key + MemoryProvider** |
| 7 | 会话记忆丢失 | ⚠️ PostSession 有但效果有限 | ❌ sync_turn 空操作 | ✅ **sync_turn 触发后台双通道提取** |

## v3 模块清单

### 新增 Butler 层 (~2.5k 行)

| 模块 | 路径 | 说明 |
|------|------|------|
| 集成入口 | `butler/main.py` | 直接 import AIAgent, 交互式 CLI |
| 编排器 | `butler/orchestrator.py` | prompt 注入, 模型配置, skill 路由 |
| Agent 角色 | `butler/agent_profiles.py` | dev/content/review 系统 prompt |
| DAG 编排 | `butler/task_orchestrator.py` | 拓扑排序, 并行/串行, 审批门控 |
| 后处理 | `butler/post_session.py` | 双通道记忆+技能提取 |
| 工具护栏 | `butler/tool_guardrails.py` | 循环检测, 重复阻断 |
| 记忆插件 | `butler/memory_plugin.py` | Hermes MemoryProvider 实现 |

### Hermes 插件注册

| 插件 | 路径 | 说明 |
|------|------|------|
| Memory Provider | `plugins/memory/butler/` | 注册 ButlerMemoryProvider |
| Gateway Hook | `plugins/butler/` | pre_gateway_dispatch 接入编排 |

### 复用的 Butler 层 (v2 已有)

| 模块 | 路径 | 说明 |
|------|------|------|
| 配置 | `butler/config.py` | 分层模型配置, Provider 管理 |
| 全局记忆 | `butler/memory/butler_memory.py` | ProfileStore + ExperienceStore |
| 项目记忆 | `butler/memory/project_memory.py` | MarkdownMemory + ProjectFacts |
| Skill 管理 | `butler/skills/manager.py` | 完整 Skill 生命周期 |
| Skill 路由 | `butler/skills/router.py` | 基于相似度的 Skill 匹配 |
| Skill 合并 | `butler/skills/consolidator.py` | LLM 驱动的 Skill 合并 |
| 报告 | `butler/report.py` | CLI / WeChat 双格式 |
| 项目管理 | `butler/project_manager.py` | 多项目切换 |

### 直接使用的 Hermes 能力 (~300k 行)

- 30+ LLM Provider (含 fallback chain, credential pool)
- 20+ Gateway (Telegram/Discord/飞书/钉钉/Slack/Matrix/邮件/短信等)
- 50+ 工具 (文件操作, shell, git, 浏览器自动化, MCP)
- Agent Loop (上下文压缩, checkpoint, 恢复)
- delegate_task (子 Agent 系统)
- Plugin 系统 (hooks, 工具注册)

## 测试验证

```
tests/test_butler_v3.py — 43 tests PASSED

TestIntegrationBridge     — 5 tests (AIAgent 构建, 配置注入)
TestMemoryPlugin          — 4 tests (注册, 工具, sync_turn)
TestButlerPlugin          — 5 tests (hook 注册, slash 命令)
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
3. **v1 产品逻辑保留**: DAG 编排、Agent Profiles、Tool Guardrails、PostSession 全部移植
4. **即刻获得 Hermes 生态**: 20+ Gateway 和 30+ Provider 开箱即用
5. **CLI 深度集成**: Butler 交互式 CLI 直接驱动 Hermes AIAgent，而非 subprocess
