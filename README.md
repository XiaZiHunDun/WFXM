# 管家系统 (Butler System)

多项目 AI 协助系统 —— 通过 CLI 或微信指挥 AI 管家管理和推进多个项目。

## 架构

```
用户 ─→ CLI / 微信 ─→ 管家(莎丽) ─→ 项目工作区
                         │
                    ┌────┴────┐
                    ▼         ▼
              Claude Code  轻量 Agent
              (代码开发)   (内容/分析)
```

**核心理念**: 管家本身是一个 AI Agent，通过 tool calling 管理项目、调度执行器，不是硬编码路由。

## 快速开始

### 1. 安装

```bash
cd /home/ailearn/projects/WFXM
pip install -e .
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env，至少配置一个 LLM Provider 的 API Key
```

### 3. 启动

```bash
# 交互式 CLI 对话
butler chat

# 执行单条指令
butler exec "列出所有项目"

# 查看项目列表
butler projects

# 创建新项目
butler create MyApp --type software --description "我的新应用"
```

## 项目结构

```
butler/
├── core/           # 管家核心 (Butler, ProjectManager, TaskOrchestrator)
├── gateway/        # 消息网关 (CLI, WeChat 适配器)
├── executors/      # 执行引擎 (Claude Code, 轻量 Agent, 工作流)
├── providers/      # LLM 提供者 (Claude, OpenAI, 国产模型)
├── storage/        # 持久化 (Session, Memory, ProjectState)
├── tools/          # 管家工具 (项目管理, 文件, Shell, 执行器, 记忆)
├── config/         # 配置和 Prompt
└── main.py         # 入口
projects/
└── LingWen/        # 灵文试点项目 (小说工厂)
```

## 支持的 LLM Provider

| Provider | 用途 | 环境变量 |
|----------|------|----------|
| Claude | 代码开发、复杂推理 | `ANTHROPIC_API_KEY` |
| OpenAI | 通用任务 | `OPENAI_API_KEY` |
| DeepSeek | 代码、中文 | `DEEPSEEK_API_KEY` |
| 通义千问 | 中文内容 | `DASHSCOPE_API_KEY` |
| 智谱 GLM | 中文内容 | `ZHIPUAI_API_KEY` |
| Moonshot | 中文长文本 | `MOONSHOT_API_KEY` |

## CLI 命令

| 命令 | 说明 |
|------|------|
| `/projects` | 列出所有项目 |
| `/switch <名称>` | 切换项目 |
| `/status` | 查看系统状态 |
| `/new` | 开始新会话 |
| `/help` | 显示帮助 |
| `/quit` | 退出 |

## 两大使用场景

### 场景 1: CLI 对话开发

直接在终端与管家对话，管家可以调用 Claude Code 进行代码修改，或使用轻量 Agent 处理内容任务。

### 场景 2: 微信远程开发

通过微信发送指令给管家，管家在后台执行任务完成后主动通知。适合移动端远程管控。

## 扩展

- **添加新 Provider**: 在 `butler/providers/` 下创建新文件，实现 `LLMProvider` 接口
- **添加新工具**: 在 `butler/tools/` 下创建新文件，使用 `@register_tool` 装饰器注册
- **添加新执行器**: 在 `butler/executors/` 下创建新文件，实现 `BaseExecutor` 接口
- **添加新网关**: 在 `butler/gateway/` 下创建新文件，实现 `BaseAdapter` 接口
